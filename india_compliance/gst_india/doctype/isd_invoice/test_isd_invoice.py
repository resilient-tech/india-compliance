# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.overrides.company import create_company_fixtures
from india_compliance.gst_india.utils.isd import bulk_create_isd_invoices
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
        test_only_service_item_taxes_in_get_purchase_invoices  is_isd_applicable=1 when PI has mixed service+goods items

    Date validation (GSTR-6 Rule 39)
        test_pi_dated_after_isd_blocks_distribution            source PI dated after the ISD invoice rejected

    Inter-company transaction validation
        test_inter_company_skipped_when_not_against_party      validation no-op when is_against_party = 0
        test_inter_company_skipped_for_non_internal_supplier   validation no-op for a non-internal supplier
        test_inter_company_allows_whitelisted_supplier         allowed internal supplier passes
        test_inter_company_allows_whitelisted_customer         allowed internal customer passes
        test_inter_company_rejects_unlisted_supplier           internal supplier not whitelisted rejected
        test_inter_company_rejects_unlisted_customer           internal customer not whitelisted rejected

    GL entries
        test_gl_entries_for_intra_company_distribution         intra-state: CGST/SGST credited at ISD GSTIN, debited at recipient
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
        invoice_names, _ = bulk_create_isd_invoices(
            distribution_table=rows, purchase_invoices=[pi.name], posting_date=pi.posting_date
        )
        self.assertEqual(_distributed_total(invoice_names), _pi_total(pi))

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
        invoice_names, _ = bulk_create_isd_invoices(
            distribution_table=rows, purchase_invoices=[pi.name], posting_date=pi.posting_date
        )
        self.assertEqual(_distributed_total(invoice_names), _pi_total(pi))

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
        isd_invoices, _ = bulk_create_isd_invoices(
            distribution_table=rows, purchase_invoices=[pi.name], posting_date=pi.posting_date
        )

        for invoice_name in isd_invoices:
            for row in frappe.get_doc("ISD Invoice", invoice_name).source_invoices:
                self.assertEqual(row.distributed_cgst, 0)
                self.assertEqual(row.distributed_sgst, 0)
                self.assertGreater(row.distributed_igst, 0)
                # single recipient => 100%: CGST + SGST + IGST all collapse into IGST (Rule 39)
                self.assertEqual(
                    flt(row.distributed_igst),
                    flt(row.total_cgst + row.total_sgst + row.total_igst),
                )

    def test_igst_input_distributed_intra_state_stays_igst(self):
        """An IGST-input PI distributed intra-state retains its IGST credit (Rule 39(1)(e)),
        it is NOT re-laid-out as CGST/SGST."""
        from india_compliance.gst_india.utils.isd import calculate_distribution

        # intra-state: company (ISD) and party both in Gujarat
        doc = self._isd()
        doc.company_pos = "24-Gujarat"
        doc.party_pos = "24-Gujarat"
        doc.append(
            "source_invoices",
            {
                "purchase_invoice": self.pi.name,
                "is_ineligible_for_itc": 0,
                "total_igst": 18000,
                "total_cgst": 0,
                "total_sgst": 0,
                "distribution_ratio": 100,
            },
        )

        calculate_distribution(doc, {})

        row = doc.source_invoices[0]
        self.assertEqual(flt(row.distributed_igst), 18000)
        self.assertEqual(flt(row.distributed_cgst), 0)
        self.assertEqual(flt(row.distributed_sgst), 0)

    def test_diffuse_returns_zero_not_none_for_zero_amount(self):
        """_diffuse must return 0.0 (not None) so distributed_* never store None."""
        from india_compliance.gst_india.utils.isd import _diffuse

        self.assertEqual(_diffuse({}, ("pi", 0, "igst"), 0, 2), 0.0)

    def test_non_gst_tax_row_is_rejected(self):
        """A non-GST tax row added by the user must raise on save (not be silently dropped)."""
        non_gst_account = frappe.db.get_value(
            "Account", {"company": self.company.name, "account_type": "Payable", "is_group": 0}, "name"
        )
        doc = self._isd()
        doc.append("taxes", {"account_head": non_gst_account, "tax_amount": 100})
        self.assertRaises(frappe.ValidationError, lambda: doc.insert(ignore_permissions=True))

    def test_invalid_tax_rows_are_collected_row_wise(self):
        """Multiple non-input-GST tax rows surface together (row-wise), not one error at a time."""
        non_gst_account = frappe.db.get_value(
            "Account", {"company": self.company.name, "account_type": "Payable", "is_group": 0}, "name"
        )
        doc = self._isd()
        doc.append("taxes", {"account_head": non_gst_account, "tax_amount": 100})
        doc.append("taxes", {"account_head": non_gst_account, "tax_amount": 200})

        with self.assertRaises(frappe.ValidationError) as cm:
            doc.insert(ignore_permissions=True)

        message = str(cm.exception)
        self.assertIn("input GST accounts", message)
        self.assertIn("Row #1", message)  # both offending rows reported
        self.assertIn("Row #2", message)

    def test_missing_input_gst_account_blocks_distribution(self):
        """A distributed amount for a GST type with no configured input account is rejected
        (the credit would otherwise be silently dropped)."""
        from india_compliance.gst_india.doctype.isd_invoice.isd_invoice import get_input_gst_accounts

        accounts = get_input_gst_accounts(self.company.name)
        missing_type = next((t for t in GST_TAX_TYPES if not accounts.get(f"{t}_account")), None)
        if not missing_type:
            self.skipTest("company has every input GST account configured")

        pi = _std_service_pi(self.company.name, self.company_isd_address.name, qty=10, rate=1000)
        isd = self._isd(source_item=_make_source_item(pi, 100))
        isd.source_invoices[0].set(f"total_{missing_type}", 100)
        isd.source_invoices[0].set(f"distributed_{missing_type}", 100)

        self.assertRaisesRegex(
            frappe.ValidationError,
            "No input GST account is configured",
            isd.insert,
            ignore_permissions=True,
        )

    def test_manual_tax_row_resolves_gst_tax_type_from_account(self):
        """A manually-added tax row (gst_tax_type is read-only) is typed from its account head, so a
        valid GST account is accepted instead of being rejected as a non-GST row."""
        from india_compliance.gst_india.doctype.isd_invoice.isd_invoice import get_input_gst_accounts

        accounts = frappe._dict(get_input_gst_accounts(self.company.name))
        pi = _std_service_pi(self.company.name, self.company_isd_address.name, qty=10, rate=1000)
        isd = self._isd(source_item=_make_source_item(pi, 100))
        isd.append("taxes", {"account_head": accounts.cgst_account, "tax_amount": 500})

        isd.insert(ignore_permissions=True)
        isd.submit()  # must not raise "Only GST tax types are allowed in Taxes"

        cgst_rows = [t for t in isd.taxes if t.gst_tax_type == "cgst"]
        self.assertEqual(len(cgst_rows), 1)
        self.assertEqual(cgst_rows[0].account_head, accounts.cgst_account)

    def test_set_pos_from_address_handles_missing_address(self):
        """set_pos_from_address must not raise when an address (or its state) is missing — the
        mandatory-field validation should surface the error instead of a raw KeyError."""
        doc = frappe.new_doc("ISD Invoice")
        doc.company = self.company.name

        doc.set_pos_from_address()  # no addresses set -> must not raise

        self.assertFalse(doc.company_pos)
        self.assertFalse(doc.party_pos)

    def test_same_company_and_party_gstin_rejected(self):
        """Credit cannot be distributed to the same GSTIN (company_gstin == party_gstin)."""
        doc = self._isd()
        doc.company_gstin = doc.party_gstin = _COMPANY_1_GSTIN
        self.assertRaises(frappe.ValidationError, doc.validate_gstins)

    def test_receipt_flow_requires_isd_party_address(self):
        """In the Credit Receipt flow the party (distributor) address must be ISD-category."""
        doc = self._isd(
            is_against_party=1,
            party_type="Supplier",
            party=self.supplier_branch.name,
            party_address=self.company_registered_address_gujarat.name,  # non-ISD -> must raise
        )
        doc.credit_flow = "Credit Receipt"
        self.assertRaises(frappe.ValidationError, doc.validate_isd_party)

    def test_only_service_item_taxes_in_get_purchase_invoices(self):
        """is_isd_applicable set to 1 on PI with mixed service + goods items at ISD billing address.

        This is the Python precondition that triggers the JS alert in purchase_invoice.js
        (frappe.show_alert when is_isd_applicable && has_goods_items).
        """
        pi = create_purchase_invoice(
            company=self.company.name,
            billing_address=self.company_isd_address.name,
            supplier="_Test Registered Supplier",
            items=[
                {
                    "item_code": "_Test Service Item",
                    "qty": 1,
                    "rate": 10000,
                    "gst_hsn_code": "999900",
                    "item_tax_template": _GST_18_TEMPLATE,
                },
                {
                    "item_code": "_Test Service Item",
                    "qty": 1,
                    "rate": 10000,
                    "gst_hsn_code": "61149090",
                    "item_tax_template": _GST_18_TEMPLATE,
                },
            ],
            is_in_state=True,
        )
        self.assertEqual(pi.is_isd_applicable, 1)

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
        self.assertRaisesRegex(frappe.ValidationError, "after this ISD invoice", isd.save)

    def test_source_invoice_problems_are_collected_row_wise(self):
        """Problems across multiple source rows surface together in one table, not one error at a
        time (old code stopped at the first failing row)."""
        pi1 = _std_service_pi(self.company.name, self.company_isd_address.name, qty=10, rate=1000)
        pi2 = _std_service_pi(self.company.name, self.company_isd_address.name, qty=5, rate=1000)

        # both PIs are dated after the ISD invoice
        isd = self._isd(
            posting_date=frappe.utils.add_months(pi1.posting_date, -1),
            source_item=_make_source_item(pi1, 50),
        )
        isd.append("source_invoices", _make_source_item(pi2, 50))
        isd.flags.ignore_validate = True
        isd.insert(ignore_permissions=True)
        isd.flags.ignore_validate = False

        with self.assertRaises(frappe.ValidationError) as cm:
            isd.save()

        message = str(cm.exception)
        self.assertIn("after this ISD invoice", message)
        self.assertIn(pi1.name, message)  # both offending rows reported, not just the first
        self.assertIn(pi2.name, message)

    def test_duplicate_source_invoices_are_rejected(self):
        """The same purchase invoice + eligibility appearing in two rows is rejected."""
        pi = _std_service_pi(self.company.name, self.company_isd_address.name, qty=10, rate=1000)
        isd = self._isd(source_item=_make_source_item(pi, 50))
        isd.append("source_invoices", _make_source_item(pi, 50))
        isd.flags.ignore_validate = True
        isd.insert(ignore_permissions=True)
        isd.flags.ignore_validate = False
        self.assertRaisesRegex(frappe.ValidationError, "added more than once", isd.save)

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

    def test_gl_entries_for_intra_company_distribution(self):
        """Intra-state: CGST/SGST credited at ISD GSTIN, debited at recipient GSTIN; debits == credits."""
        from india_compliance.gst_india.doctype.isd_invoice.isd_invoice import get_input_gst_accounts

        pi = _std_service_pi(self.company.name, self.company_isd_address.name, qty=10, rate=1000)
        # Gujarat ISD -> Gujarat registered: only CGST + SGST (no IGST for intra-state)
        isd = self._isd(source_item=_make_source_item(pi, 100))
        isd.insert(ignore_permissions=True)
        isd.submit()

        accounts = frappe._dict(get_input_gst_accounts(self.company.name))
        src = isd.source_invoices[0]

        gl_entries = frappe.get_all(
            "GL Entry",
            filters={"voucher_type": "ISD Invoice", "voucher_no": isd.name, "is_cancelled": 0},
            fields=["account", "debit", "credit", "company_gstin"],
        )
        self.assertTrue(gl_entries, "No GL entries created on submit")

        for gle in gl_entries:
            if gle.account == accounts.cgst_account:
                if gle.credit:
                    self.assertEqual(gle.credit, src.distributed_cgst)
                    self.assertEqual(gle.company_gstin, _COMPANY_1_GSTIN)
                else:
                    self.assertEqual(gle.debit, src.distributed_cgst)
                    self.assertEqual(gle.company_gstin, _COMPANY_2_GSTIN)
            elif gle.account == accounts.sgst_account:
                if gle.credit:
                    self.assertEqual(gle.credit, src.distributed_sgst)
                    self.assertEqual(gle.company_gstin, _COMPANY_1_GSTIN)
                else:
                    self.assertEqual(gle.debit, src.distributed_sgst)
                    self.assertEqual(gle.company_gstin, _COMPANY_2_GSTIN)

        self.assertEqual(
            sum(e.debit for e in gl_entries),
            sum(e.credit for e in gl_entries),
        )

    def _live_gl_entries(self, isd_name):
        return frappe.get_all(
            "GL Entry",
            filters={"voucher_type": "ISD Invoice", "voucher_no": isd_name, "is_cancelled": 0},
            fields=["account", "debit", "credit", "company_gstin", "cost_center"],
        )

    def test_gl_entries_reversed_on_cancel(self):
        """On cancel, the ISD GL entries are reversed and the PI distribution % rolls back to 0."""
        pi = _std_service_pi(self.company.name, self.company_isd_address.name, qty=10, rate=1000)
        isd = self._isd(source_item=_make_source_item(pi, 100))
        isd.insert(ignore_permissions=True)
        isd.submit()

        self.assertTrue(self._live_gl_entries(isd.name), "No GL entries on submit")
        self.assertEqual(
            flt(frappe.db.get_value("Purchase Invoice", pi.name, "isd_credit_distributed_percent")), 100
        )

        isd.cancel()

        self.assertFalse(self._live_gl_entries(isd.name), "GL entries not reversed on cancel")
        self.assertEqual(
            flt(frappe.db.get_value("Purchase Invoice", pi.name, "isd_credit_distributed_percent")), 0
        )

    def test_partial_distribution_cancel_rolls_back_pi_percent(self):
        """Cancelling one of several ISD invoices for a PI rolls its distributed % back to the rest,
        and the cancelled invoice's GL is reversed (not left live)."""
        pi = _std_service_pi(self.company.name, self.company_isd_address.name, qty=100, rate=1000)

        isd1 = self._isd(source_item=_make_source_item(pi, 50))
        isd1.insert(ignore_permissions=True)
        isd1.submit()
        isd2 = self._isd(source_item=_make_source_item(pi, 40))
        isd2.insert(ignore_permissions=True)
        isd2.submit()

        percent = lambda: flt(  # noqa: E731
            frappe.db.get_value("Purchase Invoice", pi.name, "isd_credit_distributed_percent")
        )
        self.assertEqual(percent(), 90)

        isd2.cancel()

        self.assertEqual(percent(), 50)  # only isd1's 50% remains
        self.assertFalse(self._live_gl_entries(isd2.name), "GL entries not reversed on cancel")

    def test_gl_entries_against_party_distribution_debits_party_account(self):
        """Against-party distribution: input GST is credited under the ISD GSTIN and the party account
        (Payable, for a Supplier) is debited under the party GSTIN; debits == credits."""
        pi = _std_service_pi(self.company.name, self.company_isd_address.name, qty=100, rate=1000)
        party_address = frappe.db.get_value("Supplier", self.supplier_branch.name, "supplier_primary_address")
        isd = self._isd(
            is_against_party=1,
            party_type="Supplier",
            party=self.supplier_branch.name,
            party_address=party_address,
            source_item=_make_source_item(pi, 100),
        )
        isd.credit_flow = "Credit Distribution"
        isd.insert(ignore_permissions=True)
        isd.submit()

        gl = self._live_gl_entries(isd.name)
        self.assertTrue(gl)
        self.assertEqual(sum(g.debit for g in gl), sum(g.credit for g in gl))

        party_debit = [g for g in gl if g.account == isd.party_account]
        self.assertTrue(party_debit, "party account not booked")
        self.assertTrue(all(g.debit and not g.credit for g in party_debit))
        self.assertTrue(all(g.company_gstin == _SUPPLIER_2_GSTIN for g in party_debit))
        # the Supplier party account must be a Payable account
        self.assertEqual(frappe.db.get_value("Account", isd.party_account, "account_type"), "Payable")

    def test_gl_entries_unregistered_recipient_uses_expense_account(self):
        """Unregistered recipient: input GST credited at the ISD GSTIN, debited to GST Expense (no GSTIN)."""
        from india_compliance.gst_india.doctype.isd_invoice.isd_invoice import get_input_gst_accounts

        pi = _std_service_pi(self.company.name, self.company_isd_address.name, qty=10, rate=1000)
        isd = self._isd(
            party_address=self.company_unregistered_address.name,
            source_item=_make_source_item(pi, 100),
        )
        # GST Expense is a P&L account, so (as make_isd_invoice does) its GL leg needs a cost center
        isd.expense_account = frappe.db.get_value("Company", self.company.name, "default_gst_expense_account")
        isd.cost_center = (
            frappe.db.get_value("Company", self.company.name, "cost_center") or f"Main - {self.company.abbr}"
        )
        self.assertTrue(isd.expense_account, "Company has no default GST expense account")
        isd.insert(ignore_permissions=True)
        isd.submit()

        accounts = frappe._dict(get_input_gst_accounts(self.company.name))
        input_accounts = {accounts.get(f"{t}_account") for t in GST_TAX_TYPES}
        total_tax = sum(isd.source_invoices[0].get(f"distributed_{t}") for t in GST_TAX_TYPES)
        gl_entries = self._live_gl_entries(isd.name)

        expense_debit = sum(g.debit for g in gl_entries if g.account == isd.expense_account)
        input_credit = sum(g.credit for g in gl_entries if g.account in input_accounts)
        self.assertEqual(expense_debit, total_tax)
        self.assertEqual(input_credit, total_tax)
        # the unregistered share becomes the ISD company's expense -> all legs under the ISD GSTIN
        self.assertTrue(all(g.company_gstin == _COMPANY_1_GSTIN for g in gl_entries))
        self.assertEqual(sum(g.debit for g in gl_entries), sum(g.credit for g in gl_entries))

    def test_expense_account_must_belong_to_company(self):
        """An unregistered recipient's GST Expense account must belong to the ISD company."""
        pi = _std_service_pi(self.company.name, self.company_isd_address.name, qty=10, rate=1000)
        isd = self._isd(
            party_address=self.company_unregistered_address.name,
            source_item=_make_source_item(pi, 100),
        )
        # an account from another company is not valid
        isd.expense_account = frappe.db.get_value(
            "Account", {"company": self.branch_company, "is_group": 0}, "name"
        )
        isd.cost_center = (
            frappe.db.get_value("Company", self.company.name, "cost_center") or f"Main - {self.company.abbr}"
        )
        self.assertRaisesRegex(
            frappe.ValidationError, "does not belong to Company", lambda: isd.insert(ignore_permissions=True)
        )

    def test_unregistered_recipient_defaults_cost_center_in_gl(self):
        """The unregistered-recipient credit books to a P&L GST Expense account; like Sales/Purchase
        Invoice, its GL entry falls back to the company default cost center so submit doesn't fail
        with a raw GL error."""
        pi = _std_service_pi(self.company.name, self.company_isd_address.name, qty=10, rate=1000)
        isd = self._isd(
            party_address=self.company_unregistered_address.name,
            source_item=_make_source_item(pi, 100),
        )
        isd.insert(ignore_permissions=True)
        isd.submit()  # must not raise "Cost Center is mandatory for P&L account"

        default_cc = frappe.db.get_value("Company", self.company.name, "cost_center")
        expense_gl = [g for g in self._live_gl_entries(isd.name) if g.account == isd.expense_account]
        self.assertTrue(expense_gl)
        self.assertTrue(all(g.cost_center == default_cc for g in expense_gl))

    def test_party_account_must_match_party_type(self):
        """Party Account must be a Balance Sheet account of the matching type (like Sales/Purchase)."""
        doc = self._isd(is_against_party=1, party_type="Supplier", party=self.supplier_branch.name)
        # a Receivable account is Balance Sheet but the wrong type for a Supplier (needs Payable)
        doc.party_account = frappe.db.get_value(
            "Account", {"company": self.company.name, "account_type": "Receivable", "is_group": 0}, "name"
        )
        self.assertRaisesRegex(frappe.ValidationError, "Payable account", doc.validate_party_account)

    def test_distribution_summary_query_and_extension(self):
        """The runner returns the core summary (with SQL total_tax); a caller can extend the query
        with extra Purchase Invoice columns via .select() (the report's pattern)."""
        from india_compliance.gst_india.utils.isd import (
            _get_purchase_invoices_distribution_summary,
            get_distribution_summary_query,
        )

        pi = _std_service_pi(self.company.name, self.company_isd_address.name, qty=10, rate=1000)
        expected_total = sum(sum(flt(i.get(f"{t}_amount")) for i in pi.items) for t in GST_TAX_TYPES)

        base = _get_purchase_invoices_distribution_summary([pi.name])
        self.assertEqual(len(base), 1)
        self.assertEqual(base[0].purchase_invoice, pi.name)
        self.assertEqual(flt(base[0].total_tax), flt(expected_total))
        self.assertEqual(flt(base[0].available_tax), flt(expected_total))  # nothing distributed yet
        self.assertEqual(flt(base[0].distributed_tax), 0)

        pi_dt = frappe.qb.DocType("Purchase Invoice")
        pi_item = frappe.qb.DocType("Purchase Invoice Item")
        extended = (
            get_distribution_summary_query([pi.name])
            .join(pi_dt)
            .on(pi_dt.name == pi_item.parent)
            .select(pi_dt.company_gstin, pi_dt.place_of_supply)
            .run(as_dict=True)
        )
        self.assertEqual(extended[0].company_gstin, pi.company_gstin)
        self.assertIn("place_of_supply", extended[0])


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
    """distribution_table dict for bulk_create_isd_invoices."""
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
