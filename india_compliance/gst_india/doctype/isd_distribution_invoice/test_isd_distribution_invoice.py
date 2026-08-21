# Copyright (c) 2026, Resilient Tech and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import add_months, flt, today

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.doctype.isd_distribution_invoice.isd_distribution_invoice import (
    _create_isd_recipient_invoice,
)
from india_compliance.gst_india.doctype.turnover_record.turnover_record import get_relevant_period
from india_compliance.gst_india.utils.isd import (
    bulk_create_isd_distribution_invoices,
    get_input_gst_accounts,
    get_isd_autofill_values,
    sum_row_tax_by_type,
)
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
                "is_ineligible_for_itc": item.get("is_ineligible_for_itc") or 0,
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

    # company_gstin / party_gstin are fetch_from fields that are not populated on a bare
    # new_doc, so derive them from the addresses when a caller has not set them explicitly.
    for address_field, gstin_field in (
        ("company_address", "company_gstin"),
        ("party_address", "party_gstin"),
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


def _create_isd_doc(doctype, **data):
    """Shared insert / submit flow for the ISD factories below (mirrors create_transaction)."""
    data = frappe._dict(data)
    do_not_save = data.pop("do_not_save", False)
    do_not_submit = data.pop("do_not_submit", False)

    doc = make_isd_doc(doctype, data.pop("source_items", None), **data)

    if do_not_save:
        return doc

    doc.insert()

    if not do_not_submit:
        doc.submit()

    return doc


def create_distribution_invoice(**data):
    """An ISD Distribution Invoice, built like create_sales_invoice / create_purchase_invoice.

    Pass `purchase_invoice` as a Purchase Invoice document and its items are mirrored into
    source_items. `do_not_save` / `do_not_submit` stop before insert / submit; every other key is
    set on the document.
    """
    data = frappe._dict(data)

    if (pi := data.purchase_invoice) and not isinstance(pi, str):
        data.purchase_invoice = pi.name
        data.setdefault("source_items", make_source_item(pi))

    return _create_isd_doc("ISD Distribution Invoice", **data)


def create_recipient_invoice(**data):
    """An ISD Recipient Invoice, built like create_sales_invoice / create_purchase_invoice.

    `do_not_save` / `do_not_submit` stop before insert / submit; every other key is set on the
    document.
    """
    # a manual invoice must carry the number its ISD issued, the way create_purchase_invoice
    # defaults bill_no -- pass one explicitly to test the number itself
    if not data.get("isd_distribution_invoice_reference"):
        data.setdefault("external_isd_invoice_number", frappe.generate_hash(length=8))

    return _create_isd_doc("ISD Recipient Invoice", **data)


def make_ineligible_isd_pi(billing_address, **kwargs):
    """An ISD-applicable Purchase Invoice whose single item is ineligible for ITC."""
    items = [
        {
            "item_code": "_Test Service Item",
            "qty": 1,
            "rate": 10000,
            "gst_hsn_code": "999900",
            "cost_center": "Main - _TIRC",
            "expense_account": PROFIT_AND_LOSS_ACCOUNT,
            "is_ineligible_for_itc": 1,
        }
    ]
    return make_isd_pi(billing_address, items=items, **kwargs)


# ---------------------------------------------------------------------------
# GL helpers (module level so the ISD Recipient Invoice tests can reuse them)
# ---------------------------------------------------------------------------


def get_gl_rows(doc):
    """Active (non-cancelled) GL Entries posted by an ISD document."""
    return frappe.get_all(
        "GL Entry",
        filters={"voucher_type": doc.doctype, "voucher_no": doc.name, "is_cancelled": 0},
        fields=["account", "debit", "credit", "party_type", "party", "company_gstin"],
    )


def account_totals(rows):
    """{account: {"debit": total, "credit": total}} for a set of GL rows."""
    totals = {}
    for row in rows:
        entry = totals.setdefault(row.account, {"debit": 0.0, "credit": 0.0})
        entry["debit"] += row.debit
        entry["credit"] += row.credit
    return totals


def assert_balanced_gl(test, rows):
    """The document posted something, debits equal credits, and no amount is negative."""
    test.assertTrue(rows)
    test.assertAlmostEqual(sum(row.debit for row in rows), sum(row.credit for row in rows), places=2)
    for row in rows:
        test.assertGreaterEqual(row.debit, 0)
        test.assertGreaterEqual(row.credit, 0)


def get_auto_recipient_invoice(distribution):
    """The submitted ISD Recipient Invoice auto-created for a distribution invoice."""
    name = frappe.db.get_value(
        "ISD Recipient Invoice",
        {"isd_distribution_invoice_reference": distribution.name, "docstatus": 1},
    )
    return frappe.get_doc("ISD Recipient Invoice", name)


ISD_ADDRESS = "_Test ISD Distribution-Billing"
RECIPIENT_ADDRESS = "_Test ISD Recipient-Billing"
RECIPIENT_ADDRESS_KA = "_Test ISD Recipient KA-Billing"
BRANCH_CUSTOMER_ADDRESS = "_Test ISD Branch Customer-Billing"


def setup_isd_fixtures(cls):
    """Bind the shared ISD masters (india_compliance/tests/test_records.json) onto the test class
    and raise the one ISD-applicable Purchase Invoice the source items are built from."""
    # tests assume the default behaviour (expense distributed with the ITC); the flag defaults to 1
    # on a fresh install but an existing single may have it unset, so pin it explicitly
    frappe.db.set_single_value("GST Settings", "distribute_expense_with_isd_credit", 1)

    cls.company = COMPANY
    cls.isd_address = frappe.get_doc("Address", ISD_ADDRESS)
    cls.recipient_address = frappe.get_doc("Address", RECIPIENT_ADDRESS)
    cls.recipient_address_ka = frappe.get_doc("Address", RECIPIENT_ADDRESS_KA)
    cls.branch_customer = frappe.get_doc("Customer", BRANCH_CUSTOMER)
    cls.branch_address = frappe.get_doc("Address", BRANCH_CUSTOMER_ADDRESS)
    cls.pi = make_isd_pi(cls.isd_address.name)


class IntegrationTestISDDistributionInvoice(IntegrationTestCase):
    """Basic validations and GL entries for ISD Distribution Invoice (excludes bulk generation)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        setup_isd_fixtures(cls)

    def _full_distribution(self, pi=None, branch=25, total=100, **kwargs):
        """An unsaved ISD Distribution Invoice mirroring the Purchase Invoice's items."""
        kwargs.setdefault("company_address", self.isd_address.name)
        kwargs.setdefault("party_address", self.recipient_address.name)
        kwargs.setdefault("do_not_save", True)
        return create_distribution_invoice(
            purchase_invoice=pi or self.pi, branch_turnover=branch, total_turnover=total, **kwargs
        )

    def assert_invalid_rows(self, method, title, row_value=None):
        """throw_invalid_rows renders as a list: the heading becomes the dialog title and only the
        offending rows reach the exception message, so assert on both halves."""
        frappe.clear_messages()
        with self.assertRaises(VALIDATION_ERROR) as cm:
            method()

        self.assertIn(title, frappe.message_log[-1].get("title", ""))
        if row_value:
            self.assertIn(row_value, str(cm.exception))

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

    def test_recipient_address_autofills_branch_turnover(self):
        from_date, to_date = get_relevant_period(today())

        # One Turnover Record per state per period, and submitting a distribution invoice upserts
        # turnover for its recipient's state, so clear both states this test asserts on.
        frappe.db.delete(
            "Turnover Record",
            {
                "gst_state": ["in", ("Gujarat", "Karnataka")],
                "from_date": ["<=", to_date],
                "to_date": [">=", from_date],
            },
        )
        record = frappe.get_doc(
            {
                "doctype": "Turnover Record",
                "from_date": from_date,
                "to_date": to_date,
                "gstin": RECIPIENT_GSTIN,
                "gst_state": "Gujarat",
                "amount": 7000,
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "Turnover Record", record.name, force=True)

        def branch_turnover(party_address):
            return get_isd_autofill_values(
                "ISD Distribution Invoice",
                "party_address",
                {"company": COMPANY, "party_address": party_address, "posting_date": today()},
            ).branch_turnover

        # recipient in Gujarat -> its turnover is filled from the record
        self.assertEqual(branch_turnover(self.recipient_address.name), 7000)

        # recipient in a state with no record (Karnataka) -> left empty
        self.assertIsNone(branch_turnover(self.recipient_address_ka.name))

        values = get_isd_autofill_values(
            "ISD Distribution Invoice",
            "party_address",
            {
                "company": COMPANY,
                "party_address": self.recipient_address_ka.name,
                "posting_date": today(),
                "branch_turnover": 1234,
            },
        )
        self.assertIsNone(values.branch_turnover)

        # nothing the caller sent is echoed back, so a field being edited mid-request is safe
        for field in ("company", "posting_date"):
            self.assertNotIn(field, values)

        # the recipient side never autofills a branch turnover
        # (on that doctype the recipient registration is the company's own address)
        self.assertIsNone(
            get_isd_autofill_values(
                "ISD Recipient Invoice",
                "company_address",
                {
                    "company": COMPANY,
                    "company_address": self.recipient_address.name,
                    "posting_date": today(),
                },
            ).get("branch_turnover")
        )

    # ------------------------------------------------------------------ addresses / ISD party / GSTIN
    def test_address_validations(self):
        # On the distribution side, the company owns the distribution address; one linked to a Customer
        # (not the company) is invalid.
        doc = make_distribution_invoice(company_address="_Test Registered Customer-Billing")
        self.assertRaisesRegex(
            VALIDATION_ERROR, "is not valid for this ISD distribution", doc.validate_address_links
        )

        # Against a party, the recipient address must be linked to the party, not the company.
        doc = make_distribution_invoice(
            company_address=self.isd_address.name,
            party_address=self.recipient_address.name,
            is_against_party=1,
            party_type="Customer",
            party=self.branch_customer.name,
        )
        self.assertRaisesRegex(
            VALIDATION_ERROR, "is not valid for this ISD distribution", doc.validate_address_links
        )

        # The distribution address must be of ISD category; the recipient address must not be.
        doc = make_distribution_invoice(company_address=self.recipient_address.name)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "not registered as an Input Service Distributor", doc.validate_isd_party
        )

        doc = make_distribution_invoice(party_address=self.isd_address.name)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "must not be an Input Service Distributor", doc.validate_isd_party
        )

        # A fully valid pair passes and the place of supply is derived from each address.
        doc = make_distribution_invoice(
            company_address=self.isd_address.name, party_address=self.recipient_address.name
        )
        doc.validate_addresses()
        self.assertEqual(doc.company_pos, "24-Gujarat")
        self.assertEqual(doc.party_pos, "24-Gujarat")

    def test_gstin_validations(self):
        # credit cannot be distributed to the same GSTIN
        doc = make_distribution_invoice(company_gstin=ISD_GSTIN, party_gstin=ISD_GSTIN)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "cannot be distributed to the same GSTIN", doc.validate_gstins
        )

        # the PAN of both GSTINs must be the same
        doc = make_distribution_invoice(company_gstin=ISD_GSTIN, party_gstin=MISMATCH_PAN_GSTIN)
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
        self.assert_invalid_rows(
            doc.validate_expense_heads, "not valid for Company", f"Cost of Goods Sold - {BRANCH_ABBR}"
        )

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
        doc = make_distribution_invoice(purchase_invoice=draft.name, company_gstin=ISD_GSTIN)
        self.assertRaisesRegex(VALIDATION_ERROR, "is not submitted", doc.validate_purchase_invoice)

        # must be ISD applicable (billed to a non-ISD address here)
        non_isd_pi = make_isd_pi("_Test Indian Registered Company-Billing")
        doc = make_distribution_invoice(purchase_invoice=non_isd_pi.name, company_gstin=ISD_GSTIN)
        self.assertRaisesRegex(VALIDATION_ERROR, "is not ISD applicable", doc.validate_purchase_invoice)

        # posting date must be on or after the Purchase Invoice
        doc = make_distribution_invoice(
            purchase_invoice=self.pi.name, company_gstin=ISD_GSTIN, posting_date=add_months(today(), -1)
        )
        self.assertRaisesRegex(
            VALIDATION_ERROR, "is after this ISD Distribution Invoice", doc.validate_purchase_invoice
        )

        # must belong to the same company
        doc = make_distribution_invoice(
            purchase_invoice=self.pi.name, company=BRANCH_COMPANY, company_gstin=ISD_GSTIN
        )
        self.assertRaisesRegex(
            VALIDATION_ERROR, "belongs to a different company", doc.validate_purchase_invoice
        )

        # the PI's company GSTIN must be the distribution GSTIN
        doc = make_distribution_invoice(purchase_invoice=self.pi.name, company_gstin=RECIPIENT_GSTIN)
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
        self.assert_invalid_rows(
            doc.validate_source_items, "do not belong to Purchase Invoice", "_Test Service Item"
        )

        # the same Purchase Invoice item added twice
        rows = make_source_item(self.pi)
        rows.append(dict(rows[0]))
        doc = make_distribution_invoice(purchase_invoice=self.pi.name, source_items=rows)
        doc.setup_precision()
        self.assert_invalid_rows(doc.validate_source_items, "added more than once", "_Test Service Item")

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
        self.assert_invalid_rows(doc.validate_source_items, "missing from the source items")

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
        doc = self._full_distribution(pi=pi, party_address=self.recipient_address.name)
        doc.insert()
        self.assertEqual({tax.gst_tax_type for tax in doc.taxes}, {"igst"})
        self.assertEqual(self._distributed_heads(doc), {"igst"})

    def test_intra_state_pi_same_state_distribution_keeps_cgst_sgst(self):
        # Intra-state Purchase Invoice (CGST+SGST) distributed within the same state -> both distributor
        # and recipient keep CGST+SGST.
        pi = make_isd_pi(self.isd_address.name)
        doc = self._full_distribution(pi=pi, party_address=self.recipient_address.name)
        doc.insert()
        self.assertEqual({tax.gst_tax_type for tax in doc.taxes}, {"cgst", "sgst"})
        self.assertEqual(self._distributed_heads(doc), {"cgst", "sgst"})

    def test_intra_state_pi_inter_state_distribution_recipient_igst_only(self):
        # Intra-state Purchase Invoice (CGST+SGST) distributed to a different state -> the recipient
        # receives IGST only (CGST+SGST fused), while the distributor still reduces the source CGST+SGST.
        pi = make_isd_pi(self.isd_address.name)
        doc = self._full_distribution(pi=pi, party_address=self.recipient_address_ka.name)
        doc.insert()
        self.assertEqual(self._distributed_heads(doc), {"igst"})
        self.assertEqual({tax.gst_tax_type for tax in doc.taxes}, {"cgst", "sgst"})

    # ------------------------------------------------------------------ end to end / distribution limits
    def test_invoices_excluded_from_the_isd_pool(self):
        """Reverse charge credit reaches an ISD only through a same-PAN regular registration
        (Sec 20(1) with Rule 39(1A)), and a return carries negative tax, which would distribute as
        negative source totals and a meaningless distributed percentage."""
        rcm_pi = make_isd_pi(
            self.isd_address.name,
            is_in_state=False,
            is_in_state_rcm=True,
            is_reverse_charge=1,
            supplier="_Test Unregistered Supplier",
        )
        self.assertEqual(rcm_pi.is_isd_applicable, 0)

        # and the server refuses it even if the flag is bypassed on the client
        doc = self._full_distribution(pi=rcm_pi)
        self.assertRaisesRegex(VALIDATION_ERROR, "not ISD applicable", doc.insert)

        # the shared fixture is the control: an ordinary ISD invoice is distributable, and it
        # doubles as the invoice the return is raised against
        self.assertEqual(self.pi.is_isd_applicable, 1)

        pi_return = make_isd_pi(
            self.isd_address.name,
            is_return=1,
            return_against=self.pi.name,
            qty=-1,
            do_not_submit=True,
        )
        self.assertEqual(pi_return.is_isd_applicable, 0)

        # an opening entry carries no credit to distribute
        opening_pi = make_isd_pi(self.isd_address.name, is_opening="Yes", do_not_submit=True)
        self.assertEqual(opening_pi.is_isd_applicable, 0)

    def test_against_party_recipient_invoice_is_created(self):
        """The inter-company mapper re-defaults every company-owned value onto the recipient
        company. isd_provisional_account is the party account on an against-party document, so
        seeding it with the company's Tax-type provisional account made the mapped invoice
        unsaveable."""
        pi = make_isd_pi(self.isd_address.name)
        doc = self._full_distribution(
            pi=pi,
            party_address=self.branch_address.name,
            is_against_party=1,
            party_type="Customer",
            party=self.branch_customer.name,
        )
        doc.insert()
        doc.submit()

        recipient = _create_isd_recipient_invoice(doc.name)
        recipient.reload()

        self.assertEqual(recipient.docstatus, 1)
        self.assertEqual(recipient.company, BRANCH_COMPANY)
        self.assertEqual(recipient.is_against_party, 1)

        # the distributing entity is a Supplier in the branch company's books
        self.assertEqual(recipient.party_type, "Supplier")
        self.assertEqual(recipient.party, "_Test ISD Distributor Supplier")

        # addresses invert, and both now belong to the recipient company's side
        self.assertEqual(recipient.company_address, "_Test ISD Branch Company-Billing")
        self.assertEqual(recipient.party_address, "_Test ISD Distributor Supplier-Billing")

        # the party account has to be Payable for a Supplier, and belong to the recipient company
        account_type, company = frappe.get_cached_value(
            "Account", recipient.isd_provisional_account, ["account_type", "company"]
        )
        self.assertEqual(account_type, "Payable")
        self.assertEqual(company, BRANCH_COMPANY)

        self.assertEqual(
            recipient.cost_center, frappe.get_cached_value("Company", BRANCH_COMPANY, "cost_center")
        )

    def test_cost_center_defaults_on_the_document(self):
        """The GL entries need a cost center; defaulting it at GL time would leave the document
        blank and desync it from its row, so a later save would raise UpdateAfterSubmitError."""
        company_cost_center = frappe.get_cached_value("Company", COMPANY, "cost_center")

        pi = make_isd_pi(self.isd_address.name)
        doc = self._full_distribution(pi=pi, cost_center=None)
        doc.insert()
        self.assertEqual(doc.cost_center, company_cost_center)

        doc.submit()
        self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "cost_center"), company_cost_center)

        # the same in-memory instance must still be saveable after submit
        doc.save()

    def test_grand_total_is_served_by_the_controller(self):
        pi = make_isd_pi(self.isd_address.name)
        doc = create_distribution_invoice(
            purchase_invoice=pi,
            company_address=self.isd_address.name,
            party_address=self.recipient_address.name,
        )

        expected = flt(doc.total_eligible) + flt(doc.total_ineligible) + flt(doc.total_expense)
        self.assertTrue(expected)

        # virtual: resolved through the class property, so it must survive a fresh load
        reloaded = frappe.get_doc(doc.doctype, doc.name)
        self.assertAlmostEqual(reloaded.as_dict()["grand_total"], expected, places=2)

    def test_turnover_record_is_upserted_on_submit(self):
        gstin = self.recipient_address.gstin
        from_date, to_date = get_relevant_period(today())
        frappe.db.delete(
            "Turnover Record",
            {"gstin": gstin, "from_date": from_date, "to_date": to_date},
        )

        pi = make_isd_pi(self.isd_address.name)
        doc = self._full_distribution(pi=pi, branch=25, total=100)
        doc.insert()
        doc.submit()

        record = frappe.db.get_value(
            "Turnover Record",
            {"gstin": gstin, "from_date": from_date, "to_date": to_date},
            ["amount", "gst_state"],
            as_dict=True,
        )
        self.assertIsNotNone(record)
        self.assertEqual(record.amount, 25)
        self.assertEqual(record.gst_state, self.recipient_address.gst_state)

    def test_over_distribution_is_rejected(self):
        item = {
            "item_code": "_Test Service Item",
            "qty": 1,
            "rate": 10000,
            "gst_hsn_code": "999900",
            "cost_center": "Main - _TIRC",
        }
        pi = make_isd_pi(self.isd_address.name, items=[dict(item), dict(item)])

        create_distribution_invoice(
            purchase_invoice=pi,
            company_address=self.isd_address.name,
            party_address=self.recipient_address.name,
            branch_turnover=60,
            total_turnover=100,
        )

        # a further 60% would take the total past 100%: the turnover is the user's to correct,
        # so the document is refused rather than quietly reduced to the remaining 40%
        second = self._full_distribution(pi=pi, branch=60, total=100)
        self.assertRaisesRegex(VALIDATION_ERROR, "more than Purchase Invoice", second.insert)

        # a distribution that exactly fills the remainder still goes through
        third = self._full_distribution(pi=pi, branch=40, total=100)
        third.insert()
        self.assertTrue(sum(sum_row_tax_by_type(row, "distributed") for row in third.source_items))

    def test_credit_note_over_reversal_is_rejected(self):
        pi = make_isd_pi(self.isd_address.name)
        first = create_distribution_invoice(
            purchase_invoice=pi,
            company_address=self.isd_address.name,
            party_address=self.recipient_address.name,
            branch_turnover=50,
            total_turnover=100,
        )
        distributed = sum(sum_row_tax_by_type(row, "distributed") for row in first.source_items)

        # reversing 60% against a 50% distribution would give back credit that was never passed on
        credit_note = self._full_distribution(
            pi=pi, branch=60, total=100, is_credit_note=1, credit_note_against=first.name
        )
        self.assertRaisesRegex(VALIDATION_ERROR, "more than Purchase Invoice", credit_note.insert)

        # reversing exactly what was distributed is allowed
        exact = self._full_distribution(
            pi=pi, branch=50, total=100, is_credit_note=1, credit_note_against=first.name
        )
        exact.insert()

        reversed_itc = sum(sum_row_tax_by_type(row, "distributed") for row in exact.source_items)
        self.assertAlmostEqual(reversed_itc, -distributed, places=2)

    def test_only_one_credit_note_per_distribution(self):
        """The reversal limit comes from what the distribution passed on, so a second credit note
        would be free to reverse the same credit all over again."""
        pi = make_isd_pi(self.isd_address.name)
        distribution = create_distribution_invoice(
            purchase_invoice=pi,
            company_address=self.isd_address.name,
            party_address=self.recipient_address.name,
            branch_turnover=50,
            total_turnover=100,
        )

        credit_note = self._full_distribution(
            pi=pi, branch=50, total=100, is_credit_note=1, credit_note_against=distribution.name
        )
        credit_note.insert()
        credit_note.submit()

        second = self._full_distribution(
            pi=pi, branch=50, total=100, is_credit_note=1, credit_note_against=distribution.name
        )
        self.assertRaisesRegex(VALIDATION_ERROR, "already has a credit note", second.insert)

        # a cancelled credit note does not hold the slot
        credit_note.cancel()
        replacement = self._full_distribution(
            pi=pi, branch=50, total=100, is_credit_note=1, credit_note_against=distribution.name
        )
        replacement.insert()

    def test_clamp_reduces_the_source_heads_whichever_way_the_credit_converts(self):
        """The taxes table holds the source heads while the rows hold the converted ones, so an
        intra-state purchase distributed inter-state is IGST on the rows and CGST + SGST here.
        Neither the rows nor the taxes may be left holding the surplus."""
        for label, party_address in (
            ("intra-state", self.recipient_address.name),
            ("inter-state", self.recipient_address_ka.name),
        ):
            with self.subTest(label):
                pi = make_isd_pi(self.isd_address.name)
                doc = self._full_distribution(pi=pi, party_address=party_address)
                doc.insert()

                before = {tax.gst_tax_type: tax.tax_amount for tax in doc.taxes}
                distributed_before = sum(sum_row_tax_by_type(row, "distributed") for row in doc.source_items)

                doc.setup_precision()
                doc.setup_tax_amounts()
                doc.clamp_itc_surplus(doc.get_surplus_by_tax_type(0.02))
                doc.set_tax_totals()

                after = {tax.gst_tax_type: tax.tax_amount for tax in doc.taxes}
                # the source heads survive: an empty head here is rejected by set_tax_totals
                self.assertEqual(set(after), set(before))
                self.assertTrue(all(after.values()))

                # and both sides give up the surplus, not just the rows
                distributed_after = sum(sum_row_tax_by_type(row, "distributed") for row in doc.source_items)
                self.assertAlmostEqual(distributed_before - distributed_after, 0.02, places=2)
                self.assertAlmostEqual(sum(before.values()) - sum(after.values()), 0.02, places=2)

    def test_cess_gives_up_its_own_share_of_the_surplus(self):
        """CESS is levied separately from GST but counts towards the surplus, so it has to be
        reduced too — otherwise the GST heads absorb its excess and the CESS head keeps it."""
        pi = make_isd_pi(self.isd_address.name)
        doc = self._full_distribution(pi=pi)
        doc.insert()

        row = doc.source_items[0]
        row.distributed_cess = 100
        gst = sum_row_tax_by_type(row, "distributed") - 100

        doc.setup_precision()
        surplus_by_tax_type = doc.get_surplus_by_tax_type(0.02)

        # 100 of CESS against the GST heads, so CESS carries its proportion of the 0.02 and the
        # heads the credit was distributed under carry the rest
        self.assertAlmostEqual(surplus_by_tax_type["cess"], flt(0.02 * 100 / (gst + 100), 2), places=2)
        self.assertAlmostEqual(sum(surplus_by_tax_type.values()), 0.02, places=2)

        doc.setup_tax_amounts()
        doc.clamp_itc_surplus(surplus_by_tax_type)
        self.assertAlmostEqual(flt(row.distributed_cess), 100 - surplus_by_tax_type["cess"], places=2)

    @change_settings("GST Settings", {"distribute_expense_with_isd_credit": 1})
    def test_expense_clamp_spreads_across_rows(self):
        item = {
            "item_code": "_Test Service Item",
            "qty": 1,
            "rate": 10000,
            "gst_hsn_code": "999900",
            "cost_center": "Main - _TIRC",
        }
        pi = make_isd_pi(self.isd_address.name, items=[dict(item), dict(item)])
        doc = self._full_distribution(pi=pi)
        doc.insert()

        before = [flt(row.distributed_expense) for row in doc.source_items]
        self.assertEqual(len(before), 2)
        self.assertTrue(all(before))

        doc.setup_precision()
        doc.reduce_distributed_amount("expense", 0.02)

        after = [flt(row.distributed_expense) for row in doc.source_items]
        # taken off every row that carries expense, and adding back to exactly the surplus
        self.assertAlmostEqual(sum(before) - sum(after), 0.02, places=2)
        self.assertTrue(all(a < b for a, b in zip(after, before, strict=True)))

    # ------------------------------------------------------------------ GL entries
    @change_settings("GST Settings", {"auto_create_isd_recipient_invoice": 1})
    def test_eligible_distribution_gl_entries(self):
        pi = make_isd_pi(self.isd_address.name)
        doc = create_distribution_invoice(
            purchase_invoice=pi,
            company_address=self.isd_address.name,
            party_address=self.recipient_address.name,
        )

        rows = get_gl_rows(doc)
        assert_balanced_gl(self, rows)
        totals = account_totals(rows)

        # the input GST accounts are credited (the credit leaves the ISD)
        for tax in doc.taxes:
            self.assertAlmostEqual(totals[tax.account_head]["credit"], tax.tax_amount, places=2)
            self.assertEqual(totals[tax.account_head]["debit"], 0)

        # the pro-rata expense is credited on the source item's expense head
        source_row = doc.source_items[0]
        self.assertAlmostEqual(
            totals[source_row.expense_head]["credit"], source_row.distributed_expense, places=2
        )

        # the clearing account balances the document (isd_provisional_amount = taxes + expense)
        self.assertAlmostEqual(
            totals[doc.isd_provisional_account]["debit"], doc.isd_provisional_amount, places=2
        )
        self.assertAlmostEqual(
            doc.isd_provisional_amount,
            doc.total_eligible + doc.total_ineligible + doc.total_expense,
            places=2,
        )

        # every row carries the distributor's GSTIN (mandatory on GST accounts)
        self.assertTrue(all(row.company_gstin == ISD_GSTIN for row in rows))

        # the auto-created recipient invoice posts the exact mirror
        recipient = get_auto_recipient_invoice(doc)
        recipient_rows = get_gl_rows(recipient)
        assert_balanced_gl(self, recipient_rows)
        recipient_totals = account_totals(recipient_rows)

        for tax in recipient.taxes:
            self.assertAlmostEqual(recipient_totals[tax.account_head]["debit"], tax.tax_amount, places=2)

        self.assertAlmostEqual(
            recipient_totals[recipient.isd_provisional_account]["credit"],
            recipient.isd_provisional_amount,
            places=2,
        )
        self.assertTrue(all(row.company_gstin == RECIPIENT_GSTIN for row in recipient_rows))

    @change_settings("GST Settings", {"auto_create_isd_recipient_invoice": 1})
    def test_ineligible_distribution_gl_entries(self):
        pi = make_ineligible_isd_pi(self.isd_address.name)
        doc = create_distribution_invoice(
            purchase_invoice=pi,
            company_address=self.isd_address.name,
            party_address=self.recipient_address.name,
            branch_turnover=100,
            total_turnover=300,
        )

        rows = get_gl_rows(doc)
        assert_balanced_gl(self, rows)

        source_row = doc.source_items[0]
        ineligible_tax = sum_row_tax_by_type(source_row, "distributed")
        self.assertTrue(ineligible_tax)

        # gross pairs: each tax account keeps a distinct credit (distribution) AND debit (reversal)
        for tax in doc.taxes:
            tax_rows = [row for row in rows if row.account == tax.account_head]
            self.assertEqual(len(tax_rows), 2)
            self.assertAlmostEqual(sum(row.credit for row in tax_rows), tax.tax_amount, places=2)
            self.assertAlmostEqual(sum(row.debit for row in tax_rows), tax.tax_amount, places=2)

        # the expense head gives up the ineligible tax on top of the pro-rata expense
        expense_credit = sum(row.credit for row in rows if row.account == source_row.expense_head)
        self.assertAlmostEqual(expense_credit, source_row.distributed_expense + ineligible_tax, places=2)

        # the clearing amount still includes the ineligible tax
        clearing_debit = sum(row.debit for row in rows if row.account == doc.isd_provisional_account)
        self.assertAlmostEqual(clearing_debit, doc.isd_provisional_amount, places=2)

        # mirrored on the recipient: taxes received gross, expense head absorbs the ineligible tax
        recipient = get_auto_recipient_invoice(doc)
        recipient_rows = get_gl_rows(recipient)
        assert_balanced_gl(self, recipient_rows)
        recipient_row = recipient.source_items[0]
        expense_debit = sum(row.debit for row in recipient_rows if row.account == recipient_row.expense_head)
        self.assertAlmostEqual(expense_debit, recipient_row.distributed_expense + ineligible_tax, places=2)

        # distributed inter-state the recipient takes the credit as IGST, but the distributor still
        # holds CGST and SGST, so that is what its reversal has to hit -- and to the paisa, or the
        # accounts keep a residue. The turnover ratio is a recurring third so that nothing here can
        # rely on the amount dividing evenly.
        inter_state = create_distribution_invoice(
            purchase_invoice=pi,
            company_address=self.isd_address.name,
            party_address=self.recipient_address_ka.name,
            branch_turnover=100,
            total_turnover=300,
        )
        inter_state_totals = account_totals(get_gl_rows(inter_state))
        accounts = get_input_gst_accounts(COMPANY)

        # nothing is reversed out of IGST: the distributor never held the credit there
        self.assertNotIn(accounts.igst_account, inter_state_totals)

        inter_state_row = inter_state.source_items[0]
        self.assertTrue(inter_state_row.distributed_igst)
        reversed_total = 0

        for account in (accounts.cgst_account, accounts.sgst_account):
            # distributed and reversed in full, leaving no balance behind
            self.assertEqual(inter_state_totals[account]["debit"], inter_state_totals[account]["credit"])
            reversed_total += inter_state_totals[account]["debit"]

        # the halves add back to exactly what was distributed, with no paisa lost or invented
        self.assertEqual(reversed_total, inter_state_row.distributed_igst)

    @change_settings("GST Settings", {"auto_create_isd_recipient_invoice": 1})
    def test_inter_state_distribution_gl_entries(self):
        # CGST+SGST fuse into IGST for a different-state recipient: the distributor's GL still
        # credits the source CGST+SGST while the recipient's GL debits IGST only.
        pi = make_isd_pi(self.isd_address.name)
        doc = create_distribution_invoice(
            purchase_invoice=pi,
            company_address=self.isd_address.name,
            party_address=self.recipient_address_ka.name,
        )

        accounts = get_input_gst_accounts(COMPANY)
        totals = account_totals(get_gl_rows(doc))
        self.assertIn(accounts.cgst_account, totals)
        self.assertIn(accounts.sgst_account, totals)
        self.assertNotIn(accounts.igst_account, totals)

        recipient = get_auto_recipient_invoice(doc)
        recipient_rows = get_gl_rows(recipient)
        assert_balanced_gl(self, recipient_rows)
        recipient_totals = account_totals(recipient_rows)
        self.assertNotIn(accounts.cgst_account, recipient_totals)
        self.assertNotIn(accounts.sgst_account, recipient_totals)
        self.assertAlmostEqual(
            recipient_totals[accounts.igst_account]["debit"],
            totals[accounts.cgst_account]["credit"] + totals[accounts.sgst_account]["credit"],
            places=2,
        )

    def test_credit_note_gl_entries(self):
        pi = make_isd_pi(self.isd_address.name)
        first = create_distribution_invoice(
            purchase_invoice=pi,
            company_address=self.isd_address.name,
            party_address=self.recipient_address.name,
            branch_turnover=50,
            total_turnover=100,
        )

        credit_note = create_distribution_invoice(
            purchase_invoice=pi,
            company_address=self.isd_address.name,
            party_address=self.recipient_address.name,
            branch_turnover=25,
            total_turnover=100,
            is_credit_note=1,
            credit_note_against=first.name,
        )

        rows = get_gl_rows(credit_note)
        # assert_balanced_gl also proves no negative amounts were stored
        assert_balanced_gl(self, rows)
        totals = account_totals(rows)

        # all sides are flipped: the taxes come back to the ISD, the clearing account is credited
        for tax in credit_note.taxes:
            self.assertAlmostEqual(totals[tax.account_head]["debit"], abs(tax.tax_amount), places=2)
            self.assertEqual(totals[tax.account_head]["credit"], 0)

        self.assertAlmostEqual(
            totals[credit_note.isd_provisional_account]["credit"],
            abs(credit_note.isd_provisional_amount),
            places=2,
        )

    def test_against_party_gl_entries(self):
        pi = make_isd_pi(self.isd_address.name)
        doc = self._full_distribution(
            pi=pi,
            party_address=self.branch_address.name,
            is_against_party=1,
            party_type="Customer",
            party=self.branch_customer.name,
        )
        doc.insert()
        doc.submit()

        rows = get_gl_rows(doc)
        assert_balanced_gl(self, rows)

        # the clearing rows sit on the receivable party account and carry the party
        clearing_rows = [row for row in rows if row.account == doc.isd_provisional_account]
        self.assertTrue(clearing_rows)
        for row in clearing_rows:
            self.assertEqual(row.party_type, "Customer")
            self.assertEqual(row.party, self.branch_customer.name)

        # a Payment Ledger Entry is created for the receivable row
        self.assertTrue(
            frappe.db.exists("Payment Ledger Entry", {"voucher_type": doc.doctype, "voucher_no": doc.name})
        )

    @change_settings("GST Settings", {"auto_create_isd_recipient_invoice": 1})
    def test_cancel_reverses_gl_entries(self):
        pi = make_isd_pi(self.isd_address.name)
        doc = create_distribution_invoice(
            purchase_invoice=pi,
            company_address=self.isd_address.name,
            party_address=self.recipient_address.name,
        )
        recipient = get_auto_recipient_invoice(doc)

        # The linked recipient invoice must be cancelled first. The back-link check runs after
        # the docstatus write (rolled back with the request in production), so roll back to a
        # savepoint here — test transactions do not roll back on their own.
        frappe.db.savepoint("isd_blocked_cancel")
        self.assertRaises(frappe.LinkExistsError, doc.cancel)
        frappe.db.rollback(save_point="isd_blocked_cancel")
        doc.reload()
        self.assertEqual(doc.docstatus, 1)

        recipient.cancel()
        self.assertFalse(get_gl_rows(recipient))  # no active GL entries remain

        doc.reload()
        doc.cancel()
        self.assertFalse(get_gl_rows(doc))


class IntegrationTestISDBulkDistribution(IntegrationTestCase):
    """bulk_create_isd_distribution_invoices: the bulk dialog's entry point, which raises one draft
    per recipient branch from a single Purchase Invoice."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        setup_isd_fixtures(cls)

    def setUp(self):
        self.bulk_pi = make_isd_pi(self.isd_address.name)

    def row(self, address, turnover, **overrides):
        """One line of the dialog's distribution table, as the client sends it."""
        gstin, gst_state = frappe.db.get_value("Address", address, ["gstin", "gst_state"])
        return {
            "address": address,
            "gstin": gstin,
            "gst_state": gst_state,
            "turnover_amount": turnover,
            **overrides,
        }

    def bulk(self, table, total_turnover=100, **overrides):
        return bulk_create_isd_distribution_invoices(
            purchase_invoice=self.bulk_pi.name,
            distribution_table=table,
            posting_date=overrides.get("posting_date", today()),
            total_turnover=total_turnover,
        )

    def test_one_draft_per_row_carrying_its_own_source_items(self):
        result = self.bulk(
            [
                self.row(self.recipient_address.name, 25),
                self.row(self.recipient_address_ka.name, 75),
            ]
        )
        self.assertEqual(result["failed"], [])
        self.assertEqual(len(result["invoices"]), 2)

        expected = {self.recipient_address.name: (25, 25.0), self.recipient_address_ka.name: (75, 75.0)}
        seen_rows = set()

        for name in result["invoices"]:
            doc = frappe.get_doc("ISD Distribution Invoice", name)
            branch_turnover, ratio = expected.pop(doc.party_address)

            self.assertEqual(doc.docstatus, 0)
            self.assertEqual(doc.purchase_invoice, self.bulk_pi.name)
            self.assertEqual(doc.company_address, self.isd_address.name)
            self.assertEqual(doc.branch_turnover, branch_turnover)
            self.assertEqual(doc.total_turnover, 100)
            self.assertAlmostEqual(doc.distribution_ratio, ratio, places=2)

            # the source items are copied per invoice, not shared: each draft owns its own rows and
            # every row still points at the Purchase Invoice item it was raised from
            self.assertEqual(
                {row.purchase_invoice_item for row in doc.source_items},
                {item.name for item in self.bulk_pi.items},
            )
            for row in doc.source_items:
                self.assertEqual(row.parent, doc.name)
                self.assertNotIn(row.name, seen_rows)
                seen_rows.add(row.name)

        self.assertFalse(expected)

    def test_rows_without_turnover_are_dropped(self):
        result = self.bulk(
            [
                self.row(self.recipient_address.name, 25),
                self.row(self.recipient_address_ka.name, 0),
            ]
        )
        self.assertEqual(len(result["invoices"]), 1)
        self.assertEqual(
            frappe.db.get_value("ISD Distribution Invoice", result["invoices"][0], "party_address"),
            self.recipient_address.name,
        )

        # ... and a table with nothing left to distribute is rejected outright
        self.assertRaisesRegex(
            VALIDATION_ERROR,
            "No rows with turnover to distribute",
            self.bulk,
            [self.row(self.recipient_address.name, 0)],
        )

    def test_total_turnover_must_be_positive(self):
        """The ratio divides by it, and the dialog can be submitted before the total is fetched."""
        for total in (0, -100):
            with self.subTest(total=total):
                self.assertRaisesRegex(
                    VALIDATION_ERROR,
                    "Total Turnover must be greater than zero",
                    self.bulk,
                    [self.row(self.recipient_address.name, 25)],
                    total_turnover=total,
                )

    def test_an_unsavable_row_does_not_take_the_others_down(self):
        """Each insert runs inside its own savepoint: without one, a failure part-way through would
        poison the transaction and discard every draft already created."""
        bad_address = "_Test ISD Nonexistent-Billing"
        result = self.bulk(
            [
                self.row(self.recipient_address.name, 25),
                dict(self.row(self.recipient_address_ka.name, 50), address=bad_address),
                self.row(self.recipient_address_ka.name, 25),
            ]
        )

        self.assertEqual(result["failed"], [bad_address])
        self.assertEqual(len(result["invoices"]), 2)

        # the drafts on either side of the failure survived the rollback
        for name in result["invoices"]:
            self.assertTrue(frappe.db.exists("ISD Distribution Invoice", name))

    def test_turnover_is_enqueued_for_every_row_including_one_that_failed(self):
        """The turnover a branch reported is recorded before the savepoint, so a branch whose draft
        could not be raised still contributes its turnover to next year's ratio."""
        bad_address = "_Test ISD Nonexistent-Billing"
        table = [
            self.row(self.recipient_address.name, 25),
            dict(self.row(self.recipient_address_ka.name, 75), address=bad_address),
        ]

        with patch("frappe.enqueue") as enqueue:
            self.bulk(table)

        self.assertEqual(enqueue.call_count, 1)
        args, kwargs = enqueue.call_args
        self.assertEqual(args[0], "india_compliance.gst_india.utils.isd._upsert_turnover_records")
        self.assertTrue(kwargs["enqueue_after_commit"])
        self.assertEqual(
            [
                (company, gstin, gst_state, turnover)
                for company, gstin, gst_state, turnover, _ in kwargs["data"]
            ],
            [(COMPANY, row["gstin"], row["gst_state"], row["turnover_amount"]) for row in table],
        )

    def test_against_party_rows_are_raised_against_the_party(self):
        """A branch held as a Customer is billed rather than cleared through the provisional
        account, so party_type / party have to survive the dialog."""
        result = self.bulk(
            [
                dict(
                    self.row(self.branch_address.name, 40),
                    party_type="Customer",
                    party=self.branch_customer.name,
                ),
                dict(self.row(self.recipient_address.name, 60), party_type="Company"),
            ]
        )
        self.assertEqual(result["failed"], [])

        against_party, own_branch = (
            frappe.get_doc("ISD Distribution Invoice", name) for name in result["invoices"]
        )

        self.assertEqual(against_party.is_against_party, 1)
        self.assertEqual(against_party.party_type, "Customer")
        self.assertEqual(against_party.party, self.branch_customer.name)

        # "Company" is the branch's own registration, not a party to bill
        self.assertEqual(own_branch.is_against_party, 0)
        self.assertIsNone(own_branch.party_type)
        self.assertIsNone(own_branch.party)
