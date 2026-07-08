# Copyright (c) 2026, Resilient Tech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import flt

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.doctype.isd_distribution_invoice.test_isd_distribution_invoice import (
    COMPANY,
    RECIPIENT_KA_GSTIN,
    VALIDATION_ERROR,
    account_totals,
    assert_balanced_gl,
    build_distribution,
    get_auto_recipient_invoice,
    get_gl_rows,
    link,
    make_ineligible_isd_pi,
    make_isd_address,
    make_isd_pi,
    make_recipient_invoice,
    make_source_item,
    setup_isd_fixtures,
    submit_distribution,
    teardown_isd_fixtures,
)
from india_compliance.gst_india.utils.isd import (
    get_input_gst_accounts,
    sum_row_tax_by_type,
)

# The recipient shares the distribution invoice's link chain (ISD Source Item -> Purchase Invoice
# Item -> Item Tax Template ...); those records already exist, so keep them out of dependency loading.
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


class IntegrationTestISDRecipientInvoice(IntegrationTestCase):
    """Basic validations and GL entries for ISD Recipient Invoice (excludes bulk generation)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        setup_isd_fixtures(cls)

    @classmethod
    def tearDownClass(cls):
        teardown_isd_fixtures()
        super().tearDownClass()

    def _recipient(self, **overrides):
        fields = dict(
            distribution_address=self.isd_address.name,
            recipient_address=self.recipient_address.name,
            branch_turnover=25,
            total_turnover=100,
        )
        source_items = overrides.pop("source_items", None)
        fields.update(overrides)
        return make_recipient_invoice(source_items=source_items, **fields)

    def _submit_reference(self, branch=25, total=100):
        """A submitted ISD Distribution Invoice, on its own Purchase Invoice, to reconcile against.

        The recipient invoice auto-created on submit is cancelled so the reference is free to link a
        freshly built recipient invoice under test (the duplicate-link guard allows only one
        submitted recipient per reference)."""
        pi = make_isd_pi(self.isd_address.name)
        ref = submit_distribution(
            pi, self.isd_address.name, self.recipient_address.name, branch=branch, total=total
        )
        get_auto_recipient_invoice(ref).cancel()
        return ref

    # ------------------------------------------------------------------ addresses / ISD party
    def test_address_validations(self):
        # On the recipient side the company owns the recipient address; one linked to a Customer
        # (not the company) is invalid.
        doc = self._recipient(recipient_address="_Test Registered Customer-Billing")
        self.assertRaisesRegex(
            VALIDATION_ERROR, "is not valid for this ISD distribution", doc.validate_address_links
        )

        # Against a party, the counterparty (distribution) address must be linked to the party.
        doc = self._recipient(
            recipient_address=self.recipient_address.name,
            distribution_address=self.isd_address.name,
            is_against_party=1,
            party_type="Customer",
            party=self.branch_customer.name,
        )
        self.assertRaisesRegex(
            VALIDATION_ERROR, "is not valid for this ISD distribution", doc.validate_address_links
        )

        # The distribution address must be of ISD category; the recipient address must not be.
        doc = self._recipient(distribution_address=self.recipient_address.name)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "not registered as an Input Service Distributor", doc.validate_isd_party
        )

        doc = self._recipient(recipient_address=self.isd_address.name)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "must not be an Input Service Distributor", doc.validate_isd_party
        )

        # A fully valid pair passes and the place of supply is derived from each address.
        doc = self._recipient()
        doc.validate_addresses()
        self.assertEqual(doc.distribution_pos, "24-Gujarat")
        self.assertEqual(doc.recipient_pos, "24-Gujarat")

    # ------------------------------------------------------------------ inter-state IGST-only
    def test_gst_account_type_validations(self):
        # inter-state: CGST/SGST cannot be received; only IGST is valid
        doc = self._recipient(
            recipient_address=self.recipient_address_ka.name,
            source_items=[{"item_code": "_Test Service Item", "distributed_cgst": 100}],
        )
        doc.setup_precision()
        self.assertRaisesRegex(
            VALIDATION_ERROR, "must be distributed as IGST", doc.validate_gst_account_types
        )

        # inter-state with only IGST passes
        doc = self._recipient(
            recipient_address=self.recipient_address_ka.name,
            source_items=[{"item_code": "_Test Service Item", "distributed_igst": 200}],
        )
        doc.setup_precision()
        doc.validate_gst_account_types()

        # intra-state CGST/SGST is allowed
        doc = self._recipient(
            source_items=[
                {"item_code": "_Test Service Item", "distributed_cgst": 100, "distributed_sgst": 100}
            ],
        )
        doc.setup_precision()
        doc.validate_gst_account_types()

    # ------------------------------------------------------------------ reference reconciliation
    def test_reference_mismatch_rejected(self):
        ref = self._submit_reference()

        # the referenced distribution invoice must be submitted
        pi = make_isd_pi(self.isd_address.name)
        draft = build_distribution(pi, self.isd_address.name, self.recipient_address.name)
        draft.insert()
        doc = self._recipient(isd_distribution_invoice_reference=draft.name)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "is not submitted", doc.validate_reference_distribution_invoice
        )

        # the distribution GSTIN must match the reference
        doc = self._recipient(isd_distribution_invoice_reference=ref.name)
        doc.distribution_gstin = RECIPIENT_KA_GSTIN
        self.assertRaisesRegex(
            VALIDATION_ERROR,
            "Distribution GSTIN .* does not match",
            doc.validate_reference_distribution_invoice,
        )

        # the recipient GSTIN must match the reference
        doc = self._recipient(isd_distribution_invoice_reference=ref.name)
        doc.recipient_gstin = RECIPIENT_KA_GSTIN
        self.assertRaisesRegex(
            VALIDATION_ERROR, "Recipient GSTIN .* does not match", doc.validate_reference_distribution_invoice
        )

        # the credit note status must match the reference
        doc = self._recipient(isd_distribution_invoice_reference=ref.name, is_credit_note=1)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "Credit Note status does not match", doc.validate_reference_distribution_invoice
        )

        # the distributed amounts per tax head must match the reference
        doc = self._recipient(
            isd_distribution_invoice_reference=ref.name,
            source_items=[{"item_code": "_Test Service Item", "distributed_cgst": 999999}],
        )
        doc.setup_precision()
        with self.assertRaises(VALIDATION_ERROR) as cm:
            doc.validate_reference_distribution_invoice()
        self.assertIn("CGST", str(cm.exception))

    def test_reference_reconciliation_passes(self):
        # no reference -> the reconciliation is skipped
        doc = self._recipient(source_items=[{"item_code": "_Test Service Item", "distributed_igst": 100}])
        self.assertIsNone(doc.isd_distribution_invoice_reference)
        doc.validate_reference_distribution_invoice()

        # amounts that mirror the reference exactly reconcile cleanly
        ref = self._submit_reference(branch=25, total=100)
        source_items = [
            {f"distributed_{tax}": row.get(f"distributed_{tax}") for tax in GST_TAX_TYPES}
            for row in ref.source_items
        ]
        doc = self._recipient(isd_distribution_invoice_reference=ref.name, source_items=source_items)
        doc.setup_precision()
        doc.validate_reference_distribution_invoice()

    # ------------------------------------------------------------------ smoke: full manual validate
    def test_recipient_validate_passes_for_manual_entry(self):
        doc = self._recipient(source_items=make_source_item(self.pi, ratio=0.25))
        doc.insert()
        self.assertEqual(doc.docstatus, 0)
        self.assertTrue(doc.get("taxes"))

    # ------------------------------------------------------------------ GL entries
    def test_manual_recipient_gl_entries(self):
        doc = self._recipient(source_items=make_source_item(self.pi, ratio=0.25))
        doc.insert()
        doc.submit()

        rows = get_gl_rows(doc)
        assert_balanced_gl(self, rows)
        totals = account_totals(rows)

        # the received credit is debited on the input GST accounts
        for tax in doc.taxes:
            self.assertAlmostEqual(totals[tax.account_head]["debit"], tax.tax_amount, places=2)
            self.assertEqual(totals[tax.account_head]["credit"], 0)

        # the pro-rata expense is debited on the source item's expense head
        source_row = doc.source_items[0]
        self.assertAlmostEqual(
            totals[source_row.expense_head]["debit"], source_row.distributed_expense, places=2
        )

        # the clearing account balances the document (isd_provisional_amount = taxes + expense)
        self.assertAlmostEqual(
            totals[doc.isd_provisional_account]["credit"], doc.isd_provisional_amount, places=2
        )

    def test_unregistered_recipient_books_taxes_to_gst_expense(self):
        # an unregistered branch cannot claim ITC, so the distributed taxes are booked to the GST
        # Expense account (not the input GST accounts) and the taxes table stays empty
        unregistered_address = make_isd_address(
            "_Test ISD Unregistered Branch Address",
            None,
            "Unregistered",
            "Gujarat",
            link("Company", COMPANY),
        )

        doc = self._recipient(
            recipient_address=unregistered_address.name,
            source_items=make_source_item(self.pi, ratio=0.25),
        )
        doc.insert()
        doc.submit()

        self.assertFalse(doc.taxes)
        # the provisional amount includes the taxes (now an expense) plus the distributed expense
        self.assertAlmostEqual(
            doc.isd_provisional_amount,
            doc.total_expense + doc.total_eligible + doc.total_ineligible,
            places=2,
        )

        rows = get_gl_rows(doc)
        assert_balanced_gl(self, rows)
        totals = account_totals(rows)

        # no input GST account is touched
        input_accounts = set(get_input_gst_accounts(COMPANY).values()) - {None}
        self.assertFalse([row for row in rows if row.account in input_accounts])

        # the received tax lands on the GST Expense account
        gst_expense_account = frappe.get_cached_value("Company", COMPANY, "default_gst_expense_account")
        self.assertAlmostEqual(
            totals[gst_expense_account]["debit"],
            doc.total_eligible + doc.total_ineligible,
            places=2,
        )

        # the expense head only carries the distributed expense (no tax absorbed)
        source_row = doc.source_items[0]
        expense_debit = sum(row.debit for row in rows if row.account == source_row.expense_head)
        self.assertAlmostEqual(expense_debit, source_row.distributed_expense, places=2)

        clearing_credit = sum(row.credit for row in rows if row.account == doc.isd_provisional_account)
        self.assertAlmostEqual(
            clearing_credit,
            doc.total_expense + doc.total_eligible + doc.total_ineligible,
            places=2,
        )

    def test_recipient_ineligible_gl_entries(self):
        # ineligible ITC on the recipient side is reversed through the GST Expense account, then
        # transferred to the item's expense head (cost of goods)
        pi = make_ineligible_isd_pi(self.isd_address.name)
        doc = self._recipient(source_items=make_source_item(pi, ratio=0.25))
        doc.insert()
        doc.submit()

        rows = get_gl_rows(doc)
        assert_balanced_gl(self, rows)
        totals = account_totals(rows)

        source_row = doc.source_items[0]
        ineligible_tax = sum_row_tax_by_type(source_row, "distributed")
        self.assertTrue(ineligible_tax)

        # GST Expense is only an intermediary: debited (reversal) and credited (transfer), netting zero
        gst_expense_account = frappe.get_cached_value("Company", COMPANY, "default_gst_expense_account")
        self.assertAlmostEqual(totals[gst_expense_account]["debit"], ineligible_tax, places=2)
        self.assertAlmostEqual(totals[gst_expense_account]["credit"], ineligible_tax, places=2)

        # each input GST account is received (debit) then reversed (credit): net zero when fully ineligible
        for tax in doc.taxes:
            tax_rows = [row for row in rows if row.account == tax.account_head]
            self.assertAlmostEqual(sum(r.debit for r in tax_rows), tax.tax_amount, places=2)
            self.assertAlmostEqual(sum(r.credit for r in tax_rows), tax.tax_amount, places=2)

        # the expense head absorbs the ineligible tax on top of the distributed expense
        expense_debit = sum(row.debit for row in rows if row.account == source_row.expense_head)
        self.assertAlmostEqual(expense_debit, source_row.distributed_expense + ineligible_tax, places=2)

    @change_settings("GST Settings", {"distribute_expense_with_isd_credit": 0})
    def test_expense_not_distributed_gl_entries(self):
        # expense distribution off: distributed_expense is zeroed and never booked to an expense head
        doc = self._recipient(source_items=make_source_item(self.pi, ratio=0.25))
        doc.insert()
        doc.submit()

        source_row = doc.source_items[0]
        self.assertEqual(flt(source_row.distributed_expense), 0)
        self.assertEqual(flt(doc.total_expense), 0)

        rows = get_gl_rows(doc)
        assert_balanced_gl(self, rows)
        totals = account_totals(rows)

        self.assertNotIn(source_row.expense_head, totals)
        # the provisional amount is just the taxes (no expense)
        self.assertAlmostEqual(
            doc.isd_provisional_amount, doc.total_eligible + doc.total_ineligible, places=2
        )

    @change_settings("GST Settings", {"distribute_expense_with_isd_credit": 0})
    def test_expense_off_ineligible_routes_to_provisional(self):
        # with expense off, the ineligible reversal is transferred to the ISD provisional account
        # instead of the cost-of-goods expense head
        pi = make_ineligible_isd_pi(self.isd_address.name)
        doc = self._recipient(source_items=make_source_item(pi, ratio=0.25))
        doc.insert()
        doc.submit()

        rows = get_gl_rows(doc)
        assert_balanced_gl(self, rows)
        totals = account_totals(rows)

        source_row = doc.source_items[0]
        ineligible_tax = sum_row_tax_by_type(source_row, "distributed")

        # no expense head booking (expense not distributed)
        self.assertNotIn(source_row.expense_head, totals)

        # with expense off the reversal goes straight to the provisional account; GST Expense is
        # not used as an intermediary
        gst_expense_account = frappe.get_cached_value("Company", COMPANY, "default_gst_expense_account")
        self.assertNotIn(gst_expense_account, totals)

        # the reversal is transferred to the ISD provisional (clearing) account on the debit side
        prov = totals[doc.isd_provisional_account]
        self.assertAlmostEqual(prov["debit"], ineligible_tax, places=2)
        self.assertAlmostEqual(prov["credit"], doc.isd_provisional_amount, places=2)

    def test_recipient_cancel_reverses_gl_entries(self):
        doc = self._recipient(source_items=make_source_item(self.pi, ratio=0.25))
        doc.insert()
        doc.submit()
        self.assertTrue(get_gl_rows(doc))

        doc.cancel()
        self.assertFalse(get_gl_rows(doc))  # originals and reversals are both cancelled
