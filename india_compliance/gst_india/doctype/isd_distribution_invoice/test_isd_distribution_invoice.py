# Copyright (c) 2026, Resilient Tech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_months, flt, today

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.overrides.company import create_company_fixtures
from india_compliance.gst_india.utils.isd import ISD_GST_CATEGORY, get_input_gst_accounts
from india_compliance.gst_india.utils.tests import create_purchase_invoice

# On IntegrationTestCase, the doctype test records and all link-field test record dependencies are
# recursively loaded. The ISD fixtures below are built at runtime, so keep them out of that list.
EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = [
    "Address",
    "Purchase Invoice",
    "Purchase Invoice Item",
    "Cost Center",
    "Tax Category",
    "Item",
    "UOM",
    "Item Tax Template",
    "Project",
    "Company",
    "Account",
    "ISD Distribution Invoice",
    "ISD Recipient Invoice",
    "ISD Source Item",
    "ISD Tax Item",
]

COMPANY = "_Test Indian Registered Company"

# GSTINs share the PAN of _TIRC ("AAQCA8719H") so validate_gstins' PAN match passes; they differ in
# state / entity code so they remain distinct registrations. Check digits are computed, not guessed.
_PAN = "AAQCA8719H"

# Accounts on _TIRC (looked up from the Standard chart of accounts)
RECEIVABLE_ACCOUNT = "Debtors - _TIRC"
PAYABLE_ACCOUNT = "Creditors - _TIRC"
PROFIT_AND_LOSS_ACCOUNT = "Cost of Goods Sold - _TIRC"
GROUP_ACCOUNT = "Current Assets - _TIRC"

# Second company (a branch) represented as an internal Customer, for the against-party workflow
BRANCH_COMPANY = "_Test ISD Branch Company"
BRANCH_ABBR = "_TISDB"
BRANCH_CUSTOMER = "_Test ISD Branch Customer"

VALIDATION_ERROR = frappe.exceptions.ValidationError


def gstin_with_check_digit(first_14):
    """Append the GSTIN check digit to the first 14 chars (mirrors validate_gstin_check_digit)."""
    code_points = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    mod = len(code_points)
    factor, total = 1, 0
    for char in first_14:
        digit = factor * code_points.find(char)
        total += (digit // mod) + (digit % mod)
        factor = 2 if factor == 1 else 1
    return first_14 + code_points[(mod - (total % mod)) % mod]


ISD_GSTIN = gstin_with_check_digit(f"24{_PAN}2Z")  # ISD registration, Gujarat
RECIPIENT_GSTIN = gstin_with_check_digit(f"24{_PAN}3Z")  # branch recipient, Gujarat (intra-state)
RECIPIENT_KA_GSTIN = gstin_with_check_digit(f"29{_PAN}1Z")  # branch recipient, Karnataka (inter-state)
BRANCH_GSTIN = gstin_with_check_digit(f"29{_PAN}2Z")  # against-party branch company, Karnataka
MISMATCH_PAN_GSTIN = "24AABCR6898M1ZN"  # existing fixture GSTIN with a different PAN


# ---------------------------------------------------------------------------
# Factories (module level so the ISD Recipient Invoice tests can reuse them)
# ---------------------------------------------------------------------------


def link(doctype, name):
    return [{"link_doctype": doctype, "link_name": name}]


def make_isd_address(title, gstin, gst_category, state, links, pincode="380015"):
    existing = frappe.db.get_value("Address", {"address_title": title, "address_type": "Billing"})
    if existing:
        frappe.delete_doc("Address", existing, force=True)

    return frappe.get_doc(
        {
            "doctype": "Address",
            "address_title": title,
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


def make_isd_pi(billing_address, inter_state=False, items=None, **kwargs):
    """A submitted, ISD-applicable Purchase Invoice (applicable because it is billed to an ISD address).

    inter_state=True bills to the Gujarat ISD address but sources from the supplier's Karnataka
    registration, making it a genuine inter-state supply (IGST); otherwise it is intra-state (CGST+SGST).
    """
    kwargs.setdefault("company", COMPANY)
    kwargs.setdefault("supplier", "_Test Registered Supplier")
    if inter_state:
        kwargs.setdefault("supplier_address", "_Test Registered Supplier-Billing-3")  # Karnataka (29)
        kwargs.setdefault("is_out_state", True)
    else:
        kwargs.setdefault("is_in_state", True)

    if items is not None:
        return create_purchase_invoice(billing_address=billing_address, items=items, **kwargs)

    kwargs.setdefault("item_code", "_Test Service Item")
    kwargs.setdefault("qty", 1)
    kwargs.setdefault("rate", 10000)
    return create_purchase_invoice(billing_address=billing_address, **kwargs)


def make_source_item(pi, ratio=1.0, is_credit_note=0):
    """One ISD Source Item row per Purchase Invoice item; totals mirror the PI item exactly."""
    sign = -1 if is_credit_note else 1
    rows = []
    for item in pi.items:
        totals = {f"total_{tax}": flt(item.get(f"{tax}_amount")) for tax in GST_TAX_TYPES}
        distributed = {
            f"distributed_{tax}": sign * flt(item.get(f"{tax}_amount")) * ratio for tax in GST_TAX_TYPES
        }
        rows.append(
            {
                "item_code": item.item_code,
                "purchase_invoice_item": item.name,
                "is_ineligible_for_itc": 0,
                "expense_head": item.expense_account,
                "total_expense": flt(item.base_net_amount),
                "distributed_expense": sign * flt(item.base_net_amount) * ratio,
                **totals,
                **distributed,
            }
        )
    return rows


def make_isd_doc(doctype, source_items=None, **fields):
    doc = frappe.new_doc(doctype)
    fields.setdefault("company", COMPANY)
    fields.setdefault("posting_date", today())
    fields.setdefault("branch_turnover", 25)
    fields.setdefault("total_turnover", 100)

    # distribution_gstin / recipient_gstin are fetch_from fields that are not populated on a bare
    # new_doc, so derive them from the addresses when a caller has not set them explicitly.
    for address_field, gstin_field in (
        ("distribution_address", "distribution_gstin"),
        ("recipient_address", "recipient_gstin"),
    ):
        if fields.get(address_field) and gstin_field not in fields:
            fields[gstin_field] = frappe.db.get_value("Address", fields[address_field], "gstin")

    for key, value in fields.items():
        doc.set(key, value)

    for row in source_items or []:
        doc.append("source_items", row)

    return doc


def make_distribution_invoice(source_items=None, **fields):
    return make_isd_doc("ISD Distribution Invoice", source_items, **fields)


def make_recipient_invoice(source_items=None, **fields):
    return make_isd_doc("ISD Recipient Invoice", source_items, **fields)


def build_distribution(pi, distribution_address, recipient_address, branch=25, total=100, **overrides):
    """A ready-to-insert ISD Distribution Invoice whose source items mirror the Purchase Invoice."""
    return make_distribution_invoice(
        source_items=make_source_item(pi),
        distribution_address=distribution_address,
        recipient_address=recipient_address,
        purchase_invoice=pi.name,
        branch_turnover=branch,
        total_turnover=total,
        **overrides,
    )


def submit_distribution(pi, distribution_address, recipient_address, **kwargs):
    doc = build_distribution(pi, distribution_address, recipient_address, **kwargs)
    doc.insert()
    doc.submit()
    return doc


def make_branch_company(name=BRANCH_COMPANY, abbr=BRANCH_ABBR, gstin=BRANCH_GSTIN):
    if frappe.db.exists("Company", name):
        frappe.delete_doc("Company", name, force=True)

    existing_with_abbr = frappe.db.get_value("Company", {"abbr": abbr}, "name")
    if existing_with_abbr:
        frappe.delete_doc("Company", existing_with_abbr, force=True)

    company = frappe.get_doc(
        {
            "doctype": "Company",
            "company_name": name,
            "abbr": abbr,
            "country": "India",
            "default_currency": "INR",
            "chart_of_accounts": "Standard",
            "gstin": gstin,
            "gst_category": "Registered Regular",
        }
    ).insert(ignore_permissions=True)
    create_company_fixtures(name)

    if not company.round_off_cost_center:
        company.db_set("round_off_cost_center", f"Main - {abbr}")

    return company


def make_internal_customer(
    name=BRANCH_CUSTOMER, represents_company=BRANCH_COMPANY, allowed_company=COMPANY, gstin=BRANCH_GSTIN
):
    if frappe.db.exists("Customer", name):
        frappe.delete_doc("Customer", name, force=True)

    customer = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": name,
            "customer_type": "Company",
            "is_internal_customer": 1,
            "represents_company": represents_company,
            "companies": [{"company": allowed_company}],
        }
    ).insert(ignore_permissions=True)

    address = make_isd_address(
        f"{name} Address", gstin, "Registered Regular", "Karnataka", link("Customer", customer.name), "560001"
    )
    customer.reload()
    customer.customer_primary_address = address.name
    customer.save(ignore_permissions=True)
    return customer, address


def setup_isd_fixtures(cls):
    """Shared fixtures: addresses linked to _TIRC, a submitted ISD-applicable Purchase Invoice, and a
    branch company represented as an internal Customer (for the against-party workflow)."""
    cls.company = COMPANY
    cls.isd_address = make_isd_address(
        "_Test ISD Distribution Address", ISD_GSTIN, ISD_GST_CATEGORY, "Gujarat", link("Company", COMPANY)
    )
    cls.recipient_address = make_isd_address(
        "_Test ISD Recipient Address",
        RECIPIENT_GSTIN,
        "Registered Regular",
        "Gujarat",
        link("Company", COMPANY),
    )
    cls.recipient_address_ka = make_isd_address(
        "_Test ISD Recipient Address KA",
        RECIPIENT_KA_GSTIN,
        "Registered Regular",
        "Karnataka",
        link("Company", COMPANY),
        "560001",
    )
    cls.pi = make_isd_pi(cls.isd_address.name)
    cls.branch_company = make_branch_company()
    cls.branch_customer, cls.branch_address = make_internal_customer()


def teardown_isd_fixtures():
    for doctype, name in (("Customer", BRANCH_CUSTOMER), ("Company", BRANCH_COMPANY)):
        if frappe.db.exists(doctype, name):
            try:
                frappe.delete_doc(doctype, name, force=True)
            except Exception:
                pass


class IntegrationTestISDDistributionInvoice(IntegrationTestCase):
    """Basic validations for ISD Distribution Invoice (excludes bulk generation and GL entries)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        setup_isd_fixtures(cls)

    @classmethod
    def tearDownClass(cls):
        teardown_isd_fixtures()
        super().tearDownClass()

    def _full_distribution(self, pi=None, **kwargs):
        distribution_address = kwargs.pop("distribution_address", self.isd_address.name)
        recipient_address = kwargs.pop("recipient_address", self.recipient_address.name)
        return build_distribution(pi or self.pi, distribution_address, recipient_address, **kwargs)

    @staticmethod
    def _distributed_heads(doc):
        """The GST heads the recipient actually receives (non-zero distributed_* on the source items)."""
        return {
            tax
            for tax in GST_TAX_TYPES
            if any(flt(row.get(f"distributed_{tax}")) for row in doc.source_items)
        }

    # ------------------------------------------------------------------ turnover / ratio
    def test_turnover_and_ratio_validations(self):
        # total turnover must be positive
        doc = make_distribution_invoice(total_turnover=0, branch_turnover=10)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "Total Turnover must be greater than zero", doc.validate_turnover_and_ratio
        )

        # branch turnover must be positive
        doc = make_distribution_invoice(total_turnover=100, branch_turnover=0)
        self.assertRaisesRegex(
            VALIDATION_ERROR,
            "Recipient Branch Turnover must be greater than zero",
            doc.validate_turnover_and_ratio,
        )

        # branch turnover cannot exceed total turnover
        doc = make_distribution_invoice(total_turnover=100, branch_turnover=150)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "cannot exceed Total Turnover", doc.validate_turnover_and_ratio
        )

        # the ratio is recomputed authoritatively from the turnovers
        doc = make_distribution_invoice(total_turnover=100, branch_turnover=25)
        doc.validate_turnover_and_ratio()
        self.assertEqual(doc.distribution_ratio, 25.0)

    # ------------------------------------------------------------------ addresses / ISD party / GSTIN
    def test_address_validations(self):
        # On the distribution side, the company owns the distribution address; one linked to a Customer
        # (not the company) is invalid.
        doc = make_distribution_invoice(distribution_address="_Test Registered Customer-Billing")
        self.assertRaisesRegex(
            VALIDATION_ERROR, "is not valid for this ISD distribution", doc.validate_address_links
        )

        # Against a party, the recipient address must be linked to the party, not the company.
        doc = make_distribution_invoice(
            distribution_address=self.isd_address.name,
            recipient_address=self.recipient_address.name,
            is_against_party=1,
            party_type="Customer",
            party=self.branch_customer.name,
        )
        self.assertRaisesRegex(
            VALIDATION_ERROR, "is not valid for this ISD distribution", doc.validate_address_links
        )

        # The distribution address must be of ISD category; the recipient address must not be.
        doc = make_distribution_invoice(distribution_address=self.recipient_address.name)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "not registered as an Input Service Distributor", doc.validate_isd_party
        )

        doc = make_distribution_invoice(recipient_address=self.isd_address.name)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "must not be an Input Service Distributor", doc.validate_isd_party
        )

        # A fully valid pair passes and the place of supply is derived from each address.
        doc = make_distribution_invoice(
            distribution_address=self.isd_address.name, recipient_address=self.recipient_address.name
        )
        doc.validate_addresses()
        self.assertEqual(doc.distribution_pos, "24-Gujarat")
        self.assertEqual(doc.recipient_pos, "24-Gujarat")

    def test_gstin_validations(self):
        # credit cannot be distributed to the same GSTIN
        doc = make_distribution_invoice(distribution_gstin=ISD_GSTIN, recipient_gstin=ISD_GSTIN)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "cannot be distributed to the same GSTIN", doc.validate_gstins
        )

        # the PAN of both GSTINs must be the same
        doc = make_distribution_invoice(distribution_gstin=ISD_GSTIN, recipient_gstin=MISMATCH_PAN_GSTIN)
        self.assertRaisesRegex(VALIDATION_ERROR, "must be the same", doc.validate_gstins)

    # ------------------------------------------------------------------ party account / expense heads
    def test_party_account_validations(self):
        # the party account type must match the party type (Supplier -> Payable)
        doc = make_distribution_invoice(is_against_party=1, party_type="Supplier")
        doc._party_account = RECEIVABLE_ACCOUNT
        self.assertRaisesRegex(VALIDATION_ERROR, "must be a Payable account", doc.validate_party_account)

        # the party account must be a Balance Sheet account
        doc = make_distribution_invoice(is_against_party=1, party_type="Supplier")
        doc._party_account = PROFIT_AND_LOSS_ACCOUNT
        self.assertRaisesRegex(
            VALIDATION_ERROR, "must be a Balance Sheet account", doc.validate_party_account
        )

    def test_expense_head_validations(self):
        # expense head must belong to the company
        row = make_source_item(self.pi)[0]
        row["expense_head"] = f"Cost of Goods Sold - {BRANCH_ABBR}"
        doc = make_distribution_invoice(source_items=[row])
        self.assertRaisesRegex(VALIDATION_ERROR, "not valid for Company", doc.validate_expense_heads)

        # expense head cannot be a group account
        doc = make_distribution_invoice()
        self.assertRaisesRegex(
            VALIDATION_ERROR,
            "cannot be a Group account",
            doc._validate_account,
            GROUP_ACCOUNT,
            "Expense Head",
        )

    # ------------------------------------------------------------------ tax rows / missing account
    def test_tax_row_validations(self):
        # a non-input-GST account in the taxes table is rejected, row-wise
        doc = make_distribution_invoice(source_items=make_source_item(self.pi), purchase_invoice=self.pi.name)
        doc.setup_precision()
        doc.setup_tax_amounts()
        doc.append("taxes", {"account_head": PAYABLE_ACCOUNT})
        doc.append("taxes", {"account_head": PROFIT_AND_LOSS_ACCOUNT})
        with self.assertRaises(VALIDATION_ERROR) as cm:
            doc.validate_gst_tax_rows()
        self.assertIn("Row #1", str(cm.exception))
        self.assertIn("Row #2", str(cm.exception))

    def test_missing_input_gst_account_blocks_distribution(self):
        if get_input_gst_accounts(COMPANY).get("cess_account"):
            self.skipTest("CESS input account is configured for this company")

        row = make_source_item(self.pi)[0]
        row["total_cess"] = 100  # a CESS amount with no configured CESS input account
        doc = make_distribution_invoice(source_items=[row], purchase_invoice=self.pi.name)
        doc.setup_precision()
        doc.setup_tax_amounts()
        self.assertRaisesRegex(
            VALIDATION_ERROR, "No input GST account is configured", doc.validate_missing_gst_account
        )

    # ------------------------------------------------------------------ purchase invoice
    def test_purchase_invoice_validations(self):
        # required
        doc = make_distribution_invoice()
        self.assertRaisesRegex(
            VALIDATION_ERROR, "Purchase Invoice is required", doc.validate_purchase_invoice
        )

        # must be submitted
        draft = make_isd_pi(self.isd_address.name, do_not_submit=True)
        doc = make_distribution_invoice(purchase_invoice=draft.name, distribution_gstin=ISD_GSTIN)
        self.assertRaisesRegex(VALIDATION_ERROR, "is not submitted", doc.validate_purchase_invoice)

        # must be ISD applicable (billed to a non-ISD address here)
        non_isd_pi = make_isd_pi("_Test Indian Registered Company-Billing")
        doc = make_distribution_invoice(purchase_invoice=non_isd_pi.name, distribution_gstin=ISD_GSTIN)
        self.assertRaisesRegex(VALIDATION_ERROR, "is not ISD applicable", doc.validate_purchase_invoice)

        # posting date must be on or after the Purchase Invoice
        doc = make_distribution_invoice(
            purchase_invoice=self.pi.name, distribution_gstin=ISD_GSTIN, posting_date=add_months(today(), -1)
        )
        self.assertRaisesRegex(
            VALIDATION_ERROR, "is after this ISD Distribution Invoice", doc.validate_purchase_invoice
        )

        # must belong to the same company
        doc = make_distribution_invoice(
            purchase_invoice=self.pi.name, company=BRANCH_COMPANY, distribution_gstin=ISD_GSTIN
        )
        self.assertRaisesRegex(
            VALIDATION_ERROR, "belongs to a different company", doc.validate_purchase_invoice
        )

        # the PI's company GSTIN must be the distribution GSTIN
        doc = make_distribution_invoice(purchase_invoice=self.pi.name, distribution_gstin=RECIPIENT_GSTIN)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "booked under a different Distribution GSTIN", doc.validate_purchase_invoice
        )

    # ------------------------------------------------------------------ source items 1:1 mapping
    def test_source_item_validations(self):
        # a row that does not point to an item on the Purchase Invoice
        row = make_source_item(self.pi)[0]
        row["purchase_invoice_item"] = "NON-EXISTENT-PII"
        doc = make_distribution_invoice(purchase_invoice=self.pi.name, source_items=[row])
        doc.setup_precision()
        self.assertRaisesRegex(
            VALIDATION_ERROR, "do not belong to Purchase Invoice", doc.validate_source_items
        )

        # the same Purchase Invoice item added twice
        rows = make_source_item(self.pi)
        rows.append(dict(rows[0]))
        doc = make_distribution_invoice(purchase_invoice=self.pi.name, source_items=rows)
        doc.setup_precision()
        self.assertRaisesRegex(VALIDATION_ERROR, "added more than once", doc.validate_source_items)

        # a Purchase Invoice item missing from the source items
        pi = make_isd_pi(
            self.isd_address.name,
            items=[
                {
                    "item_code": "_Test Service Item",
                    "qty": 1,
                    "rate": rate,
                    "gst_hsn_code": "999900",
                    "cost_center": "Main - _TIRC",
                    "expense_account": PROFIT_AND_LOSS_ACCOUNT,
                }
                for rate in (10000, 5000)
            ],
        )
        doc = make_distribution_invoice(purchase_invoice=pi.name, source_items=make_source_item(pi)[:1])
        doc.setup_precision()
        self.assertRaisesRegex(VALIDATION_ERROR, "missing from the source items", doc.validate_source_items)

        # source item tax total does not match the Purchase Invoice
        row = make_source_item(self.pi)[0]
        row["total_cgst"] = flt(row["total_cgst"]) + 10
        doc = make_distribution_invoice(purchase_invoice=self.pi.name, source_items=[row])
        doc.setup_precision()
        with self.assertRaises(VALIDATION_ERROR) as cm:
            doc.validate_source_items()
        self.assertIn("CGST", str(cm.exception))

        # source item expense does not match the Purchase Invoice
        row = make_source_item(self.pi)[0]
        row["total_expense"] = flt(row["total_expense"]) + 10
        doc = make_distribution_invoice(purchase_invoice=self.pi.name, source_items=[row])
        doc.setup_precision()
        with self.assertRaises(VALIDATION_ERROR) as cm:
            doc.validate_source_items()
        self.assertIn("Expense", str(cm.exception))

        # a valid 1:1 mapping passes
        doc = make_distribution_invoice(purchase_invoice=self.pi.name, source_items=make_source_item(self.pi))
        doc.setup_precision()
        doc.validate_source_items()

    # ------------------------------------------------------------------ distribution workflows (Rule 39)
    def test_igst_pi_same_state_distribution_stays_igst(self):
        # Inter-state Purchase Invoice (IGST) distributed within the same state -> IGST stays IGST on
        # both the distributor (taxes) and the recipient (distributed_*). Rule 39(1)(e).
        pi = make_isd_pi(self.isd_address.name, inter_state=True)
        doc = self._full_distribution(pi=pi, recipient_address=self.recipient_address.name)
        doc.insert()
        self.assertEqual({tax.gst_tax_type for tax in doc.taxes}, {"igst"})
        self.assertEqual(self._distributed_heads(doc), {"igst"})

    def test_intra_state_pi_same_state_distribution_keeps_cgst_sgst(self):
        # Intra-state Purchase Invoice (CGST+SGST) distributed within the same state -> both distributor
        # and recipient keep CGST+SGST.
        pi = make_isd_pi(self.isd_address.name)
        doc = self._full_distribution(pi=pi, recipient_address=self.recipient_address.name)
        doc.insert()
        self.assertEqual({tax.gst_tax_type for tax in doc.taxes}, {"cgst", "sgst"})
        self.assertEqual(self._distributed_heads(doc), {"cgst", "sgst"})

    def test_intra_state_pi_inter_state_distribution_recipient_igst_only(self):
        # Intra-state Purchase Invoice (CGST+SGST) distributed to a different state -> the recipient
        # receives IGST only (CGST+SGST fused), while the distributor still reduces the source CGST+SGST.
        pi = make_isd_pi(self.isd_address.name)
        doc = self._full_distribution(pi=pi, recipient_address=self.recipient_address_ka.name)
        doc.insert()
        self.assertEqual(self._distributed_heads(doc), {"igst"})
        self.assertEqual({tax.gst_tax_type for tax in doc.taxes}, {"cgst", "sgst"})

    # ------------------------------------------------------------------ end to end / distribution limits
    def test_against_party_validate_passes(self):
        pi = make_isd_pi(self.isd_address.name)
        doc = self._full_distribution(
            pi=pi,
            recipient_address=self.branch_address.name,
            is_against_party=1,
            party_type="Customer",
            party=self.branch_customer.name,
        )
        doc.insert()
        self.assertEqual(doc.docstatus, 0)

    def test_valid_distribution_submits(self):
        pi = make_isd_pi(self.isd_address.name)
        doc = self._full_distribution(pi=pi, branch=25, total=100)
        doc.insert()
        doc.submit()
        self.assertEqual(doc.docstatus, 1)
        self.assertTrue(doc.get("taxes"))

    def test_over_distribution_rejected(self):
        # A fresh Purchase Invoice keeps this test's submitted distribution from leaking into others.
        pi = make_isd_pi(self.isd_address.name)
        submit_distribution(pi, self.isd_address.name, self.recipient_address.name, branch=100, total=100)

        second = self._full_distribution(pi=pi, branch=1, total=100)
        self.assertRaisesRegex(VALIDATION_ERROR, "Over-distribution", second.insert)

    def test_credit_note_over_reversal_rejected(self):
        pi = make_isd_pi(self.isd_address.name)
        first = submit_distribution(
            pi, self.isd_address.name, self.recipient_address.name, branch=50, total=100
        )

        credit_note = self._full_distribution(
            pi=pi, branch=60, total=100, is_credit_note=1, credit_note_against=first.name
        )
        self.assertRaisesRegex(VALIDATION_ERROR, "Over-reversal", credit_note.insert)
