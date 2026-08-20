# Copyright (c) 2026, Resilient Tech and Contributors
# See license.txt

import re

import frappe
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import add_months, flt, getdate

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.doctype.isd_distribution_invoice.test_isd_distribution_invoice import (
    COMPANY,
    RECIPIENT_KA_GSTIN,
    VALIDATION_ERROR,
    account_totals,
    assert_balanced_gl,
    create_distribution_invoice,
    create_recipient_invoice,
    get_auto_recipient_invoice,
    get_gl_rows,
    link,
    make_ineligible_isd_pi,
    make_isd_address,
    make_isd_pi,
    make_source_item,
    setup_isd_fixtures,
)
from india_compliance.gst_india.overrides.test_purchase_invoice import _gstr3b_filed
from india_compliance.gst_india.utils.isd import (
    get_input_gst_accounts,
    sum_row_tax_by_type,
)
from india_compliance.gst_india.utils.itc_claim import (
    ITC_CLAIM_PERIOD_DEFERRED,
    format_period,
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

    def _recipient(self, **overrides):
        fields = dict(
            party_address=self.isd_address.name,
            company_address=self.recipient_address.name,
            branch_turnover=25,
            total_turnover=100,
            do_not_save=True,
        )
        fields.update(overrides)
        return create_recipient_invoice(**fields)

    def _submit_reference(self, branch=25, total=100):
        """A submitted ISD Distribution Invoice, on its own Purchase Invoice, to reconcile against.

        The recipient invoice auto-created on submit is cancelled so the reference is free to link a
        freshly built recipient invoice under test (the duplicate-link guard allows only one
        submitted recipient per reference)."""
        pi = make_isd_pi(self.isd_address.name)
        ref = create_distribution_invoice(
            purchase_invoice=pi,
            company_address=self.isd_address.name,
            party_address=self.recipient_address.name,
            branch_turnover=branch,
            total_turnover=total,
        )
        get_auto_recipient_invoice(ref).cancel()
        return ref

    # ------------------------------------------------------------------ addresses / ISD party
    def test_address_validations(self):
        # On the recipient side the company owns the recipient address; one linked to a Customer
        # (not the company) is invalid.
        doc = self._recipient(company_address="_Test Registered Customer-Billing")
        self.assertRaisesRegex(
            VALIDATION_ERROR, "is not valid for this ISD distribution", doc.validate_address_links
        )

        # Against a party, the counterparty (distribution) address must be linked to the party.
        doc = self._recipient(
            company_address=self.recipient_address.name,
            party_address=self.isd_address.name,
            is_against_party=1,
            party_type="Customer",
            party=self.branch_customer.name,
        )
        self.assertRaisesRegex(
            VALIDATION_ERROR, "is not valid for this ISD distribution", doc.validate_address_links
        )

        # The distribution address must be of ISD category; the recipient address must not be.
        doc = self._recipient(party_address=self.recipient_address.name)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "not registered as an Input Service Distributor", doc.validate_isd_party
        )

        doc = self._recipient(company_address=self.isd_address.name)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "must not be an Input Service Distributor", doc.validate_isd_party
        )

        # A fully valid pair passes and the place of supply is derived from each address.
        doc = self._recipient()
        doc.validate_addresses()
        self.assertEqual(doc.party_pos, "24-Gujarat")
        self.assertEqual(doc.company_pos, "24-Gujarat")

    # ------------------------------------------------------------------ inter-state IGST-only
    def test_gst_account_type_validations(self):
        def setup(doc):
            doc.setup_precision()
            doc.set_pos_from_address()

        # inter-state: CGST/SGST cannot be received; only IGST is valid
        doc = self._recipient(
            company_address=self.recipient_address_ka.name,
            source_items=[{"item_code": "_Test Service Item", "distributed_cgst": 100}],
        )
        setup(doc)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "must be distributed as IGST", doc.validate_gst_account_types
        )

        # inter-state with only IGST passes
        doc = self._recipient(
            company_address=self.recipient_address_ka.name,
            source_items=[{"item_code": "_Test Service Item", "distributed_igst": 200}],
        )
        setup(doc)
        doc.validate_gst_account_types()

        # intra-state CGST/SGST is allowed
        doc = self._recipient(
            source_items=[
                {"item_code": "_Test Service Item", "distributed_cgst": 100, "distributed_sgst": 100}
            ],
        )
        setup(doc)
        doc.validate_gst_account_types()

    # ------------------------------------------------------------------ reference reconciliation
    @change_settings("GST Settings", {"auto_create_isd_recipient_invoice": 1})
    def test_reference_mismatch_rejected(self):
        ref = self._submit_reference()

        # the referenced distribution invoice must be submitted
        pi = make_isd_pi(self.isd_address.name)
        draft = create_distribution_invoice(
            purchase_invoice=pi,
            company_address=self.isd_address.name,
            party_address=self.recipient_address.name,
            do_not_submit=True,
        )
        doc = self._recipient(isd_distribution_invoice_reference=draft.name)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "is not submitted", doc.validate_reference_distribution_invoice
        )

        # the distribution GSTIN must match the reference
        doc = self._recipient(isd_distribution_invoice_reference=ref.name)
        doc.party_gstin = RECIPIENT_KA_GSTIN
        self.assertRaisesRegex(
            VALIDATION_ERROR,
            "Distribution GSTIN .* does not match",
            doc.validate_reference_distribution_invoice,
        )

        # the recipient GSTIN must match the reference
        doc = self._recipient(isd_distribution_invoice_reference=ref.name)
        doc.company_gstin = RECIPIENT_KA_GSTIN
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

    @change_settings("GST Settings", {"auto_create_isd_recipient_invoice": 1})
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
            company_address=unregistered_address.name,
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

    @change_settings("GST Settings", {"distribute_expense_with_isd_credit": 0})
    def test_unregistered_recipient_expenses_tax_when_expense_not_distributed(self):
        """Whether the net amount travels with the credit says nothing about unclaimable tax: an
        unregistered branch must expense it either way. Booking it back to the provisional account
        posted a self-cancelling pair and stranded the credit in the clearing account."""
        unregistered_address = make_isd_address(
            "_Test ISD Unregistered Branch No Expense",
            None,
            "Unregistered",
            "Gujarat",
            link("Company", COMPANY),
        )

        doc = self._recipient(
            company_address=unregistered_address.name,
            source_items=make_source_item(self.pi, ratio=0.25),
        )
        doc.insert()
        doc.submit()

        rows = get_gl_rows(doc)
        assert_balanced_gl(self, rows)

        tax_received = doc.total_eligible + doc.total_ineligible
        self.assertTrue(tax_received)

        gst_expense_account = frappe.get_cached_value("Company", COMPANY, "default_gst_expense_account")
        totals = account_totals(rows)
        self.assertAlmostEqual(totals[gst_expense_account]["debit"], tax_received, places=2)

        # the clearing account is relieved, not left holding a debit and a credit of the same amount
        provisional_rows = [row for row in rows if row.account == doc.isd_provisional_account]
        self.assertTrue(provisional_rows)
        self.assertAlmostEqual(sum(row.credit for row in provisional_rows), tax_received, places=2)
        self.assertAlmostEqual(sum(row.debit for row in provisional_rows), 0, places=2)

    def test_manual_credit_note_must_reverse_credit(self):
        """A recipient invoice typed in against an external ISD skips the reference reconciliation,
        so nothing else checks the sign. Positive amounts on a credit note debit the input GST
        accounts again -- claiming the credit a second time instead of giving it back, and
        inflating 4(A)(4) of GSTR-3B rather than reducing it."""
        doc = self._recipient(
            is_credit_note=1,
            external_isd_invoice_number="ISD-EXT-CN-001",
            source_items=make_source_item(self.pi, ratio=0.25),
        )
        self.assertRaisesRegex(frappe.ValidationError, "must be negative in credit note", doc.insert)

        # entered as a reversal, it saves
        doc = self._recipient(
            is_credit_note=1,
            external_isd_invoice_number="ISD-EXT-CN-002",
            source_items=make_source_item(self.pi, ratio=0.25, is_credit_note=1),
        )
        doc.insert()
        self.assertLess(sum(sum_row_tax_by_type(row, "distributed") for row in doc.source_items), 0)

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

    # ------------------------------------------------------------------ ITC claim period
    def create_receipent_doc(self, **overrides):
        doc = self._recipient(
            source_items=make_source_item(self.pi, ratio=0.25), do_not_save=False, **overrides
        )

        # An update-after-submit always happens in a later request against a freshly loaded
        # document. Return a new instance so the tests below see only what was persisted --
        # reload() would keep submit-time attributes that are not docfields, and carrying that
        # state over would skip the very branches under test.
        return frappe.get_doc(doc.doctype, doc.name)

    def test_itc_claim_period_auto_set_on_submit(self):
        doc = self.create_receipent_doc()
        self.assertEqual(doc.itc_claim_period, format_period(doc.posting_date))

    def test_itc_claim_period_invalid_format(self):
        doc = self._recipient(source_items=make_source_item(self.pi, ratio=0.25))
        doc.itc_claim_period = "132024"  # Invalid: Month > 12

        self.assertRaisesRegex(
            VALIDATION_ERROR,
            re.compile(r"ITC Claim Period '.*' must be in MMYYYY format"),
            doc.insert,
        )

    def test_itc_claim_period_deferred_is_retained(self):
        doc = self.create_receipent_doc(itc_claim_period=ITC_CLAIM_PERIOD_DEFERRED)

        self.assertEqual(doc.itc_claim_period, ITC_CLAIM_PERIOD_DEFERRED)

    def test_itc_claim_period_change_unfiled_to_unfiled(self):
        doc = self.create_receipent_doc()

        next_period = format_period(add_months(doc.posting_date, 1))
        doc.itc_claim_period = next_period
        doc.save()
        doc.reload()

        self.assertEqual(doc.itc_claim_period, next_period)

    def test_itc_claim_period_update_restriction_when_filed(self):
        """Once GSTR-3B is filed for the claimed period, the period cannot be moved away from it."""
        doc = self.create_receipent_doc()
        current_period = doc.itc_claim_period

        with _gstr3b_filed(doc.company_gstin, doc.posting_date):
            # move to another period -> blocked
            doc.itc_claim_period = format_period(add_months(doc.posting_date, 1))
            self.assertRaisesRegex(
                VALIDATION_ERROR,
                re.compile(r"Cannot change ITC Claim Period from .* to .*\. GSTR-3B already filed for .*\."),
                doc.save,
            )

            # move to Deferred -> also blocked
            doc.reload()
            doc.itc_claim_period = ITC_CLAIM_PERIOD_DEFERRED
            self.assertRaisesRegex(
                VALIDATION_ERROR,
                re.compile(r"Cannot change ITC Claim Period from .* to .*\. GSTR-3B already filed for .*\."),
                doc.save,
            )

        # period is unfiled again -> the same change is allowed
        doc.reload()
        self.assertEqual(doc.itc_claim_period, current_period)
        doc.itc_claim_period = ITC_CLAIM_PERIOD_DEFERRED
        doc.save()

        self.assertEqual(doc.itc_claim_period, ITC_CLAIM_PERIOD_DEFERRED)

    def test_itc_claim_period_change_to_filed_period_blocked(self):
        """Cannot move the claim period INTO a period whose GSTR-3B is already filed."""
        doc = self.create_receipent_doc()
        next_date = getdate(add_months(doc.posting_date, 1))

        with _gstr3b_filed(doc.company_gstin, next_date):
            doc.itc_claim_period = format_period(next_date)
            self.assertRaisesRegex(
                VALIDATION_ERROR,
                re.compile(r"GSTR-3B already filed"),
                doc.save,
            )

    def test_recipient_cancel_reverses_gl_entries(self):
        doc = self._recipient(source_items=make_source_item(self.pi, ratio=0.25))
        doc.insert()
        doc.submit()
        self.assertTrue(get_gl_rows(doc))

        doc.cancel()
        self.assertFalse(get_gl_rows(doc))  # originals and reversals are both cancelled
