# Copyright (c) 2026, Resilient Tech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_months, flt, today

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.doctype.isd_distribution_invoice.isd_distribution_invoice import (
    create_isd_recipient_invoice,
)
from india_compliance.gst_india.overrides.company import create_company_fixtures
from india_compliance.gst_india.utils.isd import (
    ISD_GST_CATEGORY,
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
    # The recipient mirror is created client-side after submit in production (a confirm decides
    # whether to auto-submit it); mirror that here so tests get the submitted intra-company recipient.
    if not doc.is_against_party:
        create_isd_recipient_invoice(doc.name, submit_on_creation=1)
    return doc


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
    from india_compliance.gst_india.overrides.company import (
        make_default_gst_expense_accounts,
        make_default_isd_provisional_account,
    )

    # the test company may predate these company fixtures (idempotent)
    make_default_isd_provisional_account(COMPANY)
    make_default_gst_expense_accounts(COMPANY)

    # tests assume the default behaviour (expense distributed with the ITC); the flag defaults to 1
    # on a fresh install but an existing single may have it unset, so pin it explicitly
    frappe.db.set_single_value("GST Settings", "distribute_expense_with_isd_credit", 1)

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


def _delete_isd_docs_for_party(party_type, party):
    """Cancel and delete any ISD documents raised against a party so it can be deleted."""
    for distribution in frappe.get_all(
        "ISD Distribution Invoice", filters={"party_type": party_type, "party": party}, pluck="name"
    ):
        for recipient in frappe.get_all(
            "ISD Recipient Invoice",
            filters={"isd_distribution_invoice_reference": distribution},
            pluck="name",
        ):
            _cancel_and_delete("ISD Recipient Invoice", recipient)
        _cancel_and_delete("ISD Distribution Invoice", distribution)


def _cancel_and_delete(doctype, name):
    doc = frappe.get_doc(doctype, name)
    if doc.docstatus == 1:
        doc.cancel()
    frappe.delete_doc(doctype, name, force=True)


def teardown_isd_fixtures():
    _delete_isd_docs_for_party("Customer", BRANCH_CUSTOMER)
    for doctype, name in (("Customer", BRANCH_CUSTOMER), ("Company", BRANCH_COMPANY)):
        if frappe.db.exists(doctype, name):
            frappe.delete_doc(doctype, name, force=True)


class IntegrationTestISDDistributionInvoice(IntegrationTestCase):
    """Basic validations and GL entries for ISD Distribution Invoice (excludes bulk generation)."""

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

    def test_recipient_address_autofills_branch_turnover(self):
        # The distribution side pulls the Recipient Branch Turnover from the Turnover Record matching
        # the recipient's state (narrowed by GSTIN) for the invoice's fiscal year.
        from erpnext.accounts.utils import get_fiscal_year

        _, from_date, to_date = get_fiscal_year(today())

        # one Turnover Record per state per period, so clear any overlapping Gujarat record first
        frappe.db.delete(
            "Turnover Record",
            {"gst_state": "Gujarat", "from_date": ["<=", to_date], "to_date": [">=", from_date]},
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

        def branch_turnover(recipient_address):
            return get_isd_autofill_values(
                "ISD Distribution Invoice",
                "recipient_address",
                {"company": COMPANY, "recipient_address": recipient_address, "posting_date": today()},
            ).branch_turnover

        # recipient in Gujarat -> its turnover is filled from the record
        self.assertEqual(branch_turnover(self.recipient_address.name), 7000)

        # recipient in a state with no record (Karnataka) -> left empty
        self.assertIsNone(branch_turnover(self.recipient_address_ka.name))

        # a manually entered turnover is kept when no record matches
        self.assertEqual(
            get_isd_autofill_values(
                "ISD Distribution Invoice",
                "recipient_address",
                {
                    "company": COMPANY,
                    "recipient_address": self.recipient_address_ka.name,
                    "posting_date": today(),
                    "branch_turnover": 1234,
                },
            ).branch_turnover,
            1234,
        )

        # the recipient side never autofills a branch turnover
        self.assertIsNone(
            get_isd_autofill_values(
                "ISD Recipient Invoice",
                "recipient_address",
                {
                    "company": COMPANY,
                    "recipient_address": self.recipient_address.name,
                    "posting_date": today(),
                },
            ).get("branch_turnover")
        )

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

    def test_over_distribution_is_clamped_to_available(self):
        pi = make_isd_pi(self.isd_address.name)
        first = submit_distribution(
            pi, self.isd_address.name, self.recipient_address.name, branch=60, total=100
        )

        available = sum(sum_row_tax_by_type(row, "total") for row in first.source_items)
        already = sum(sum_row_tax_by_type(row, "distributed") for row in first.source_items)

        # a further 60% would take the total past 100%; only the remaining 40% may be drawn
        second = self._full_distribution(pi=pi, branch=60, total=100)
        second.insert()

        distributed = sum(sum_row_tax_by_type(row, "distributed") for row in second.source_items)
        self.assertAlmostEqual(distributed, available - already, places=2)

    def test_credit_note_over_reversal_is_clamped(self):
        pi = make_isd_pi(self.isd_address.name)
        first = submit_distribution(
            pi, self.isd_address.name, self.recipient_address.name, branch=50, total=100
        )
        distributed = sum(sum_row_tax_by_type(row, "distributed") for row in first.source_items)

        # reversing 60% against a 50% distribution is capped at the 50% actually distributed
        credit_note = self._full_distribution(
            pi=pi, branch=60, total=100, is_credit_note=1, credit_note_against=first.name
        )
        credit_note.insert()

        reversed_itc = sum(sum_row_tax_by_type(row, "distributed") for row in credit_note.source_items)
        self.assertAlmostEqual(reversed_itc, -distributed, places=2)

    # ------------------------------------------------------------------ GL entries
    def test_eligible_distribution_gl_entries(self):
        pi = make_isd_pi(self.isd_address.name)
        doc = submit_distribution(pi, self.isd_address.name, self.recipient_address.name)

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

    def test_ineligible_distribution_gl_entries(self):
        pi = make_ineligible_isd_pi(self.isd_address.name)
        doc = submit_distribution(pi, self.isd_address.name, self.recipient_address.name)

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

    def test_inter_state_distribution_gl_entries(self):
        # CGST+SGST fuse into IGST for a different-state recipient: the distributor's GL still
        # credits the source CGST+SGST while the recipient's GL debits IGST only.
        pi = make_isd_pi(self.isd_address.name)
        doc = submit_distribution(pi, self.isd_address.name, self.recipient_address_ka.name)

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
        first = submit_distribution(
            pi, self.isd_address.name, self.recipient_address.name, branch=50, total=100
        )

        credit_note = build_distribution(
            pi,
            self.isd_address.name,
            self.recipient_address.name,
            branch=25,
            total=100,
            is_credit_note=1,
            credit_note_against=first.name,
        )
        credit_note.insert()
        credit_note.submit()

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
            recipient_address=self.branch_address.name,
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

    def test_cancel_reverses_gl_entries(self):
        pi = make_isd_pi(self.isd_address.name)
        doc = submit_distribution(pi, self.isd_address.name, self.recipient_address.name)
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
