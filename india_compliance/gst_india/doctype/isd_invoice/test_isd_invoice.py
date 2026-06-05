# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.doctype.isd_invoice.isd_invoice import bulk_create_isd_invoices
from india_compliance.gst_india.overrides.company import create_company_fixtures
from india_compliance.gst_india.utils.tests import create_purchase_invoice
from india_compliance.tests.erpnext_test_utils import create_fiscal_year

IGNORE_TEST_RECORD_DEPENDENCIES = [
    "ISD Invoice",
    "Purchase Invoice",
    "Cost Center",
    "Project",
    "Company",
    "Account",
    "Address",
    "Item",
    "Item Tax Template",
    "UOM",
    "Tax Category",
    "Location",
    "Branch",
    "Department",
]

# Test GSTINs — Gujarat (24) / Karnataka (29), fictional PANs, shared PAN root for inter-company
_COMPANY_1_GSTIN = "24AAACI1681G3ZT"  # ISD company / its supplier+customer — Gujarat
_COMPANY_2_GSTIN = "24AAACI1681G1ZV"  # Branch (non-ISD) — Gujarat
_COMPANY_3_GSTIN = "29AAACI1681G1ZL"  # Branch — Karnataka
_SUPPLIER_1_GSTIN = _CUSTOMER_1_GSTIN = _COMPANY_1_GSTIN
_SUPPLIER_2_GSTIN = _CUSTOMER_2_GSTIN = _COMPANY_2_GSTIN

# Item tax template from create_company_fixtures for the ISD company (abbr _TISD).
# Without it, service items have zero GST rate and the PI carries no tax to distribute.
_GST_18_TEMPLATE = "GST 18% - _TISD"

# Distributed tax field names used in assertions and aggregation.
_TAX_FIELDS = [
    "distributed_cgst",
    "distributed_sgst",
    "distributed_igst",
    "distributed_cess",
    "distributed_cess_non_advol",
]


class TestISDInvoice(IntegrationTestCase):
    """
    ISD Invoice tests, grouped by concern.

    Distribution limits & credit notes
        test_distribution_cannot_exceed_100_percent            >100% distribution rejected; credit note frees capacity
        test_credit_note_cannot_exceed_originally_distributed  credit note reversing more than distributed rejected
        test_make_credit_note_negates_distribution             make_credit_note() maps invoice -> negated credit note

    Distribution accuracy
        test_distribution_conserves_total_tax                  distributed taxes sum back to original PI taxes
        test_rounding_remainder_absorbed_by_last_invoice       last invoice absorbs the 1/3-ratio rounding remainder
        test_sez_recipient_distributed_as_igst_only            SEZ recipient -> IGST only, even intra-state
        test_only_service_item_taxes_in_get_purchase_invoices  alert shown when purchase invoice has goods items only

    Date validation (GSTR-6 Rule 39)
        test_pi_dated_after_isd_blocks_distribution            source PI dated after the ISD invoice rejected

    Inter-company transaction validation
        test_inter_company_skipped_when_not_against_party      validation no-op when is_against_party = 0
        test_inter_company_skipped_for_non_internal_supplier   validation no-op for a non-internal supplier
        test_inter_company_allows_whitelisted_supplier         allowed internal supplier passes
        test_inter_company_allows_whitelisted_customer         allowed internal customer passes
        test_inter_company_rejects_unlisted_supplier           internal supplier not whitelisted rejected
        test_inter_company_rejects_unlisted_customer           internal customer not whitelisted rejected
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = _make_company("_Test ISD Company", "_TISD", _COMPANY_1_GSTIN)
        c = cls.company.name
        _create_current_fiscal_year(c)

        # Company 1 addresses: attr -> (suffix, gstin, category, state, pincode)
        for attr, suffix, gstin, cat, state, pin in [
            (
                "company_isd_address",
                "ISD",
                _COMPANY_1_GSTIN,
                "Input Service Distributor",
                "Gujarat",
                "380015",
            ),
            (
                "company_registered_address_gujarat",
                "Registered-Gujarat",
                _COMPANY_2_GSTIN,
                "Registered Regular",
                "Gujarat",
                "380015",
            ),
            (
                "company_registered_address_karnataka",
                "Registered-Karnataka",
                _COMPANY_3_GSTIN,
                "Registered Regular",
                "Karnataka",
                "560001",
            ),
            ("company_unregistered_address", "Unregistered", "", "Unregistered", "Gujarat", "380015"),
        ]:
            setattr(cls, attr, _make_address(f"{c}-{suffix}", gstin, cat, state, _link("Company", c), pin))

        # Company 2: sister / branch of Company 1 (non-ISD, Registered Regular)
        cls.branch_company = "_Test ISD Branch Company"
        _make_company(cls.branch_company, "_TISDB", _COMPANY_2_GSTIN)

        # Internal branch parties allowed to transact with Company 1.
        cls.supplier_branch = _make_internal_supplier(
            "_Test ISD Internal Supplier Branch",
            cls.branch_company,
            [c],
            _SUPPLIER_2_GSTIN,
            "Registered Regular",
            "Gujarat",
        )
        cls.customer_branch = _make_internal_customer(
            "_Test ISD Internal Customer Branch",
            cls.branch_company,
            [c],
            _CUSTOMER_2_GSTIN,
            "Registered Regular",
            "Gujarat",
        )

        cls.pi = _std_service_pi(
            c, cls.company_isd_address.name, qty=1000, rate=1000, use_company_roundoff_cost_center=True
        )
        # cgst = sgst = 90,000 for this PI

        # Duplicate ISD company + parties NOT allowed to transact (no companies whitelisted).
        cls.duplicate_isd_company = "_Test Duplicate ISD Company"
        _make_company(cls.duplicate_isd_company, "_TISDC", _COMPANY_1_GSTIN)
        cls.internal_supplier_not_allowed = _make_internal_supplier(
            "_Test ISD Internal Supplier Not Allowed",
            cls.duplicate_isd_company,
            [],
            _SUPPLIER_1_GSTIN,
            "Registered Regular",
            "Gujarat",
        )
        cls.internal_customer_not_allowed = _make_internal_customer(
            "_Test ISD Internal Customer Not Allowed",
            cls.duplicate_isd_company,
            [],
            _CUSTOMER_1_GSTIN,
            "Registered Regular",
            "Gujarat",
        )

    def _isd(self, **kwargs):
        """ISD Invoice with Company-1 defaults (company + ISD/registered addresses); override via kwargs."""
        kwargs.setdefault("company", self.company.name)
        kwargs.setdefault("company_address", self.company_isd_address.name)
        kwargs.setdefault("party_address", self.company_registered_address_gujarat.name)
        return _make_isd_doc(**kwargs)

    # --- Distribution limits & credit notes ---

    def test_distribution_cannot_exceed_100_percent(self):
        """Distributing > 100% raises ValidationError; a submitted ISD credit note frees capacity."""
        pi = _std_service_pi(self.company.name, self.company_isd_address.name, qty=100, rate=1000)

        def build(ratio, cn=0):
            return self._isd(is_credit_note=cn, source_item=_make_source_item(pi, ratio, cn))

        # 100% distributes cleanly
        isd1 = build(100)
        isd1.insert(ignore_permissions=True)
        isd1.submit()

        # Another 1% fails on save (already 100% distributed)
        isd2 = build(1)
        isd2.flags.ignore_validate = True
        isd2.insert(ignore_permissions=True)
        isd2.flags.ignore_validate = False
        self.assertRaisesRegex(frappe.ValidationError, "Available", isd2.save)

        # Credit note returns 1% — frees capacity
        cn = build(1, cn=1)
        cn.insert(ignore_permissions=True)
        cn.submit()

        # Retry isd2 — 1% freed, save passes
        isd2.reload()
        isd2.save()

    def test_credit_note_cannot_exceed_originally_distributed(self):
        """ISD credit note reversing more than was distributed raises ValidationError."""
        pi = _std_service_pi(self.company.name, self.company_isd_address.name, qty=10, rate=1000)

        isd = self._isd(source_item=_make_source_item(pi, 50))  # distribute 50%
        isd.insert(ignore_permissions=True)
        isd.submit()

        cn = self._isd(
            is_credit_note=1, source_item=_make_source_item(pi, 60, is_credit_note=1)
        )  # reverse 60% > 50%
        cn.flags.ignore_validate = True
        cn.insert(ignore_permissions=True)
        cn.flags.ignore_validate = False
        self.assertRaisesRegex(frappe.ValidationError, "Originally Distributed", cn.save)

    def test_make_credit_note_negates_distribution(self):
        """make_credit_note maps a submitted ISD invoice to a credit note with negated distribution."""
        from india_compliance.gst_india.doctype.isd_invoice.isd_invoice import make_credit_note

        pi = _std_service_pi(self.company.name, self.company_isd_address.name, qty=100, rate=1000)
        isd = self._isd(source_item=_make_source_item(pi, 100))
        isd.insert(ignore_permissions=True)
        isd.submit()

        cn = make_credit_note(isd.name)
        self.assertEqual(cn.is_credit_note, 1)
        self.assertEqual(cn.credit_note_against, isd.name)
        self.assertEqual(len(cn.source_invoices), 1)

        cn_row, src_row = cn.source_invoices[0], isd.source_invoices[0]
        for field in _TAX_FIELDS:
            self.assertEqual(cn_row.get(field), -1 * src_row.get(field))
        self.assertEqual(
            cn_row.total_cgst, src_row.total_cgst
        )  # total_* describe source PI tax, stay positive

        cn.insert(ignore_permissions=True)
        cn.submit()

    # --- Distribution accuracy ---

    def test_distribution_conserves_total_tax(self):
        """Distributed taxes across all ISD invoices sum back to the original PI taxes (no rounding drift)."""
        pi = self.pi
        fy = get_fiscal_year(pi.posting_date, company=pi.company)[0]
        rows = [
            _distribution_row(
                "",
                "Unregistered",
                "Gujarat",
                1000000,
                self.company_unregistered_address.name,
                self.company.name,
                fy,
            ),
            _distribution_row(
                _COMPANY_2_GSTIN,
                "Registered Regular",
                "Gujarat",
                1000000,
                self.company_registered_address_gujarat.name,
                self.company.name,
                fy,
            ),
            _distribution_row(
                _COMPANY_3_GSTIN,
                "Registered Regular",
                "Karnataka",
                1000000,
                self.company_registered_address_karnataka.name,
                self.company.name,
                fy,
            ),
        ]
        invoice_names, _ = bulk_create_isd_invoices(distribution_heads=rows, source_names=[pi.name])
        self.assertEqual(_distributed_total(invoice_names), _pi_total(pi))

    # TODO: ask lakshit bhai — float math: 16666666.666666666 * 6 = 99999999.99999996 (wrong),
    # but the same value added six times = 100000000.0 (float rounding "accidentally" correct).
    def test_rounding_remainder_absorbed_by_last_invoice(self):
        """Last ISD invoice absorbs the rounding remainder so total distributed == PI total.

        CGST = SGST ≈ 100000; 3 equal turnovers (ratio 1/3) → one invoice gets 33333.34, the other two 33333.33.
        """
        pi = _std_service_pi(
            self.company.name, self.company_isd_address.name, qty=1, rate=(100 / 18) * 200000000
        )
        fy = get_fiscal_year(pi.posting_date, company=pi.company)[0]
        addr = self.company_registered_address_gujarat.name
        rows = [
            _distribution_row("", "Unregistered", "Gujarat", 1000000, addr, self.company.name, fy),
            _distribution_row(
                _COMPANY_2_GSTIN, "Registered Regular", "Gujarat", 1000000, addr, self.company.name, fy
            ),
            _distribution_row(
                _COMPANY_3_GSTIN, "Registered Regular", "Karnataka", 1000000, addr, self.company.name, fy
            ),
        ]
        invoice_names, _ = bulk_create_isd_invoices(distribution_heads=rows, source_names=[pi.name])
        self.assertEqual(_distributed_total(invoice_names), _pi_total(pi))

    # TODO: party being overseas / sez
    def test_sez_recipient_distributed_as_igst_only(self):
        """SEZ recipient is distributed as IGST only, even for intra-state supply."""
        pi = self.pi  # place of supply Gujarat, intra-state
        sez_address = _make_address(
            f"{self.company.name}-SEZ",
            "24AAACI1681G2ZU",
            "SEZ",
            "Gujarat",
            _link("Company", self.company.name),
        )
        fy = get_fiscal_year(pi.posting_date, company=pi.company)[0]
        rows = [
            _distribution_row(
                "24AAACI1681G2ZU", "SEZ", "Gujarat", 1000000, sez_address.name, self.company.name, fy
            )
        ]
        isd_invoices, _ = bulk_create_isd_invoices(distribution_heads=rows, source_names=[pi.name])

        for invoice_name in isd_invoices:
            for row in frappe.get_doc("ISD Invoice", invoice_name).source_invoices:
                self.assertEqual(row.distributed_cgst, 0)
                self.assertEqual(row.distributed_sgst, 0)
                self.assertGreater(row.distributed_igst, 0)

    def test_only_service_item_taxes_in_get_purchase_invoices(self):
        """get_purchase_invoices shows alert when purchase invoice has goods items only (no service items)."""
        from unittest.mock import patch

        pi = create_purchase_invoice(
            company=self.company.name,
            billing_address=self.company_isd_address.name,
            supplier="_Test Registered Supplier",
            items=[
                {
                    "item_code": "_Test Service Item",
                    "qty": 1,
                    "rate": 10000,
                    "gst_hsn_code": "61149090",
                    "gst_treatment": "Exempted",
                }
            ],
            is_in_state=True,
        )

        isd_doc = self._isd()
        with patch.object(frappe, "msgprint") as mock_msgprint:
            isd_doc.get_purchase_invoices(purchase_invoices=[pi.name], distribution_ratio=100.0)
            mock_msgprint.assert_called_once()

        self.assertEqual(len(isd_doc.source_invoices), 0)

    # --- Date validation (GSTR-6 Rule 39) ---

    def test_pi_dated_after_isd_blocks_distribution(self):
        """Source PI dated after the ISD invoice raises ValidationError (GSTR-6 Rule 39)."""
        pi = _std_service_pi(self.company.name, self.company_isd_address.name, qty=10, rate=1000)

        # ISD posted a month before the PI — PI is in the future relative to ISD
        isd = self._isd(
            posting_date=frappe.utils.add_months(pi.posting_date, -1),
            source_item=_make_source_item(pi, 100),
        )
        isd.flags.ignore_validate = True
        isd.insert(ignore_permissions=True)
        isd.flags.ignore_validate = False
        self.assertRaisesRegex(frappe.ValidationError, "dated after this ISD invoice", isd.save)

    # --- Inter-company transaction validation ---

    def test_inter_company_skipped_when_not_against_party(self):
        self._isd(is_against_party=0).validate_inter_company_transaction()

    def test_inter_company_skipped_for_non_internal_supplier(self):
        if not frappe.db.exists("Supplier", "_Test Supplier"):
            frappe.get_doc(
                {
                    "doctype": "Supplier",
                    "supplier_name": "_Test Supplier",
                    "supplier_group": "All Supplier Groups",
                    "supplier_type": "Company",
                }
            ).insert(ignore_permissions=True)
        self._isd(
            is_against_party=1, party_type="Supplier", party="_Test Supplier"
        ).validate_inter_company_transaction()

    def test_inter_company_allows_whitelisted_supplier(self):
        self._isd(
            is_against_party=1, party_type="Supplier", party=self.supplier_branch.name
        ).validate_inter_company_transaction()

    def test_inter_company_allows_whitelisted_customer(self):
        self._isd(
            is_against_party=1, party_type="Customer", party=self.customer_branch.name
        ).validate_inter_company_transaction()

    def test_inter_company_rejects_unlisted_supplier(self):
        self._assert_not_allowed("Supplier", self.internal_supplier_not_allowed.name)

    def test_inter_company_rejects_unlisted_customer(self):
        self._assert_not_allowed("Customer", self.internal_customer_not_allowed.name)

    def _assert_not_allowed(self, party_type, party):
        doc = self._isd(is_against_party=1, party_type=party_type, party=party)
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"is not allowed to transact with Company"),
            doc.validate_inter_company_transaction,
        )

    # TODO: party being overseas


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _link(doctype, name):
    return [{"link_doctype": doctype, "link_name": name}]


def _create_current_fiscal_year(company):
    today = frappe.utils.getdate(frappe.utils.today())
    year = today.year if today.month >= 4 else today.year - 1
    create_fiscal_year(company, f"{year}-04-01", f"{year + 1}-03-31")


def _pi_total(pi):
    return sum(getattr(r, f"{tax_type}_amount") for r in pi.items for tax_type in GST_TAX_TYPES)


def _distributed_total(invoice_names):
    return sum(
        getattr(row, f)
        for name in invoice_names
        for row in frappe.get_doc("ISD Invoice", name).source_invoices
        for f in _TAX_FIELDS
    )


def _make_company(company_name, abbr, gstin, gst_category="Registered Regular", parent_company=None):
    if frappe.db.exists("Company", company_name):
        frappe.delete_doc("Company", company_name, force=True)

    # Also clear any different company that already holds the same abbreviation.
    existing_with_abbr = frappe.db.get_value("Company", {"abbr": abbr}, "name")
    if existing_with_abbr:
        frappe.delete_doc("Company", existing_with_abbr, force=True)

    doc = frappe.get_doc(
        {
            "doctype": "Company",
            "company_name": company_name,
            "abbr": abbr,
            "country": "India",
            "default_currency": "INR",
            "chart_of_accounts": "Standard",
            "gstin": gstin,
            "gst_category": gst_category,
        }
    )
    if parent_company:
        doc.parent_company = parent_company
    doc.insert(ignore_permissions=True)
    create_company_fixtures(company_name)

    # Round off cost center is not always set on a freshly inserted test company,
    # which breaks Purchase Invoice GL entry creation (make_precision_loss_gl_entry).
    if not doc.round_off_cost_center:
        doc.db_set("round_off_cost_center", f"Main - {abbr}")

    return doc


def _make_address(name, gstin, gst_category, state, links, pincode="380015"):
    if frappe.db.exists("Address", name):
        frappe.delete_doc("Address", name, force=True)

    return frappe.get_doc(
        {
            "doctype": "Address",
            "name": name,
            "address_title": name,
            "address_type": "Billing",
            "address_line1": "Test Address Line 1",
            "city": "Test City",
            "state": state,
            "pincode": pincode,
            "country": "India",
            "gstin": gstin,
            "gst_category": gst_category,
            "is_primary_address": 1,
            "links": links,
        }
    ).insert(ignore_permissions=True)


def _make_isd_doc(
    company,
    company_address=None,
    party_address=None,
    is_credit_note=0,
    is_against_party=0,
    party_type=None,
    party=None,
    posting_date=None,
    source_item=None,
):
    doc = frappe.new_doc("ISD Invoice")
    doc.company = company
    doc.posting_date = posting_date or frappe.utils.today()
    doc.is_against_party = is_against_party
    doc.is_credit_note = is_credit_note
    doc.party_type = party_type
    doc.party = party
    if company_address:
        doc.company_address = company_address
    if party_address:
        doc.party_address = party_address
    if source_item:
        doc.append("source_invoices", source_item)
    return doc


def _make_source_item(pi, ratio, is_credit_note=0):
    """source_invoices row dict; credit notes store distributed amounts negative (reverse of original)."""
    sign = -1 if is_credit_note else 1
    totals = {
        "total_igst": sum(r.igst_amount for r in pi.items),
        "total_cgst": sum(r.cgst_amount for r in pi.items),
        "total_sgst": sum(r.sgst_amount for r in pi.items),
        "total_cess": sum(r.cess_amount for r in pi.items),
        "total_cess_non_advol": sum(r.cess_non_advol_amount for r in pi.items),
    }
    distributed = {f"distributed_{k[len('total_') :]}": sign * v * ratio / 100 for k, v in totals.items()}
    return frappe._dict(
        purchase_invoice=pi.name,
        is_ineligible_for_itc=0,
        distribution_ratio=ratio,
        **totals,
        **distributed,
    )


def _std_service_pi(company, billing_address, qty=1, rate=10000, hsn="999800", **kwargs):
    """Standard single service-item PI used across most tests."""
    return create_purchase_invoice(
        company=company,
        billing_address=billing_address,
        supplier="_Test Registered Supplier",
        items=[
            {
                "item_code": "_Test Service Item",
                "qty": qty,
                "rate": rate,
                "gst_hsn_code": hsn,
                "item_tax_template": _GST_18_TEMPLATE,
            }
        ],
        is_in_state=True,
        **kwargs,
    )


def _distribution_row(gstin, gst_category, gst_state, turnover, party_address, party, fiscal_year):
    """distribution_heads dict for bulk_create_isd_invoices."""
    return {
        "gstin": gstin,
        "gst_category": gst_category,
        "gst_state": gst_state,
        "turnover_amount": turnover,
        "party_address": party_address,
        "party_type": "Company",
        "party": party,
        "fiscal_year": fiscal_year,
    }


def _make_internal_party(
    doctype, party_name, represents_company, allowed_companies, gstin, gst_category, state
):
    if frappe.db.exists(doctype, party_name):
        frappe.delete_doc(doctype, party_name, force=True)

    pt = doctype.lower()  # "supplier" or "customer"
    data = {"doctype": doctype, f"{pt}_name": party_name, f"{pt}_type": "Company", f"is_internal_{pt}": 1}
    if doctype == "Supplier":
        data["supplier_group"] = "All Supplier Groups"

    party = frappe.get_doc(data)
    if represents_company:
        party.represents_company = represents_company
    for company in allowed_companies:
        party.append("companies", {"company": company})
    party.insert(ignore_permissions=True)

    address = _make_address(f"{party_name}-Billing", gstin, gst_category, state, _link(doctype, party.name))
    party.reload()
    setattr(party, f"{pt}_primary_address", address.name)
    party.save(ignore_permissions=True)
    return party


def _make_internal_supplier(name, represents_company, allowed_companies, gstin, gst_category, state):
    return _make_internal_party(
        "Supplier", name, represents_company, allowed_companies, gstin, gst_category, state
    )


def _make_internal_customer(name, represents_company, allowed_companies, gstin, gst_category, state):
    return _make_internal_party(
        "Customer", name, represents_company, allowed_companies, gstin, gst_category, state
    )
