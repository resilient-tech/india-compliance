# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt, getdate

from india_compliance.gst_india.utils.tests import (
    create_journal_entry,
    create_purchase_invoice,
    create_transaction,
)
from india_compliance.income_tax_india.doctype.msme_registration.test_msme_registration import (
    COMPANY,
    MSME_SUPPLIER_WITHOUT_AGREEMENT,
    MSMEReportTestCase,
)
from india_compliance.income_tax_india.report.msme_disallowance_report.msme_disallowance_report import (
    execute,
)
from india_compliance.income_tax_india.utils.msme import MSME_UNCLASSIFIED


class _TestMSME43BHBase(MSMEReportTestCase):
    def _run(self, supplier, **extra_filters):
        """Run for FY 2023-2024. The position is always taken at to_date, so
        there is no as-on date to pass - see MSME43BHDisallowance.validate_filters.
        """
        _columns, data = execute(
            {
                "company": COMPANY,
                "from_date": "2023-04-01",
                "to_date": "2024-03-31",
                "supplier": supplier,
                **extra_filters,
            }
        )
        return {row["voucher_no"]: row for row in data}

    def _make_advance(self, supplier, payable_account, posting_date, amount):
        """Payment to the supplier not allocated against any voucher."""
        pe = create_transaction(
            doctype="Payment Entry",
            company=COMPANY,
            payment_type="Pay",
            mode_of_payment="Cash",
            party_type="Supplier",
            party=supplier,
            paid_from=self._get_cash_account(),
            paid_to=payable_account,
            paid_amount=amount,
            posting_date=posting_date,
            set_posting_time=1,
            reference_no="TEST",
            reference_date=posting_date,
            do_not_save=True,
        )
        pe.setup_party_account_field()
        pe.set_missing_values()
        pe.set_exchange_rate()
        pe.received_amount = pe.paid_amount / pe.target_exchange_rate
        pe.save()
        pe.submit()
        return pe

    @staticmethod
    def _get_cash_account():
        return frappe.db.get_value("Company", COMPANY, "default_cash_account") or (
            frappe.db.get_value("Account", {"company": COMPANY, "account_type": "Cash", "is_group": 0})
        )


class TestMSME43BHReport(_TestMSME43BHBase):
    def test_unpaid_overdue_is_disallowed(self):
        # Posted 2023-05-01 -> due 2023-06-15. Unpaid as on 2024-03-31 -> disallowed.
        pi = self._pi(self.supplier, "2023-05-01", 10000)
        rows = self._run(self.supplier)
        row = rows[pi.name]
        self.assertEqual(row["payment_status"], "Unpaid - Overdue")
        self.assertEqual(flt(row["outstanding_overdue"]), 10000)
        self.assertEqual(flt(row["outstanding"]), 10000)

    def test_paid_late_within_fy_is_allowed_not_disallowed(self):
        # Due 2023-06-15, paid 2023-08-01 (late but WITHIN FY 2023-24). 43B(h)
        # allows the deduction in the year of actual payment = same FY, so it
        # is NOT disallowed and does not appear in the disallowance statement
        # (visible in Form-1's invoice-wise view instead).
        pi = self._pi(self.supplier, "2023-05-01", 5000)
        self._pay(pi, "2023-08-01")
        rows = self._run(self.supplier)
        self.assertNotIn(pi.name, rows)

    def test_unpaid_at_year_end_disallowed_even_if_paid_next_fy(self):
        # Due 2023-06-15, still unpaid at FY-end 2024-03-31 -> disallowed in
        # 2023-24. A payment in a LATER year does not undo that add-back: the
        # position is taken at to_date, never as on today.
        pi = self._pi(self.supplier, "2023-05-01", 7000)
        self._pay(pi, "2024-05-01")  # paid in FY 2024-25, after the FY-end

        row = self._run(self.supplier)[pi.name]

        self.assertEqual(flt(row["outstanding"]), 7000)
        self.assertEqual(flt(row["outstanding_overdue"]), 7000)

    def test_paid_on_time_not_disallowed(self):
        # Due 2023-06-15, paid 2023-06-01 (on time) -> not in the statement.
        pi = self._pi(self.supplier, "2023-05-01", 3000)
        self._pay(pi, "2023-06-01")
        rows = self._run(self.supplier)
        self.assertNotIn(pi.name, rows)

    def test_medium_supplier_excluded(self):
        medium = self._create_msme_supplier(enterprise_type="Medium")
        pi = self._pi(medium, "2023-05-01", 9000)
        rows = self._run(medium)
        # Medium is not 43B(h)-applicable -> no rows.
        self.assertNotIn(pi.name, rows)

    def test_trader_excluded(self):
        trader = self._create_msme_supplier(enterprise_type="Small", activity="Trading")
        pi = self._pi(trader, "2023-05-01", 9000)
        rows = self._run(trader)
        self.assertNotIn(pi.name, rows)

    def test_enterprise_type_filter_narrows_within_applicable(self):
        # The type filter narrows Micro vs Small; it never widens the report
        # past 43B(h) applicability (a Medium filter shows nothing).
        medium = self._create_msme_supplier(enterprise_type="Medium")
        self._pi(medium, "2023-05-01", 9000)
        self.assertEqual(self._run(medium, enterprise_type="Medium"), {})

        micro_pi = self._pi(self.supplier, "2023-05-01", 6000)
        rows = self._run(self.supplier, enterprise_type="Micro")
        self.assertIn(micro_pi.name, rows)
        self.assertTrue(all(row["enterprise_type"] == "Micro" for row in rows.values()))

    def test_supply_before_the_registration_date_is_excluded(self):
        """Registered on Udyam in November: a June supply was not made to an MSE
        at all, so no part of it is disallowable.
        """
        supplier = self._create_msme_supplier(enterprise_type="Micro", registration_date="2023-11-01")
        before = self._pi(supplier, "2023-06-01", 5000)
        on_the_day = self._pi(supplier, "2023-11-01", 5000)

        rows = self._run(supplier)

        self.assertNotIn(before.name, rows)
        self.assertIn(on_the_day.name, rows)

    def test_unclassified_supplier_is_reported(self):
        # live registration, no classification for the invoice's FY
        supplier = self._create_msme_supplier(enterprise_type="Micro", financial_year="2024-2025")
        pi = self._pi(supplier, "2023-05-01", 4000)

        row = self._run(supplier)[pi.name]

        self.assertEqual(row["enterprise_type"], MSME_UNCLASSIFIED)
        # status unknown, so the Act's outer limit applies: 2023-05-01 -> 2023-06-15
        self.assertEqual(row["due_date"], getdate("2023-06-15"))
        self.assertEqual(flt(row["outstanding_overdue"]), 4000)


class TestMSME43BHDueDate(_TestMSME43BHBase):
    """Section 15 MSMED Act sets the limit, and 45 days is only its ceiling:

    pay by the date agreed in writing, and in no case beyond 45 days; where
    there is no written agreement at all, the limit is 15 days.

    Each case posts close enough to FY-end that the agreed date and the 45-day
    ceiling fall on opposite sides of it - that is the only place the two rules
    give different answers for this report.
    """

    def test_the_agreed_date_applies_but_never_beyond_45_days(self):
        # Each posts close enough to FY-end that the agreed date and the 45-day
        # ceiling fall on opposite sides of it - the only place the two differ.
        early = self._pi(self.supplier, "2024-02-15", 8000, due_date="2024-03-16")  # 30-day terms
        capped = self._pi(self.supplier, "2024-01-05", 4000, due_date="2024-04-04")  # 90-day terms
        # ERPNext defaults due_date to the posting date when no terms are set;
        # that is its default, not a same-day agreement
        no_terms = self._pi(self.supplier, "2024-01-01", 3000, due_date="2024-01-01")

        rows = self._run(self.supplier)

        self.assertEqual(rows[early.name]["due_date"], getdate("2024-03-16"))
        self.assertEqual(rows[early.name]["days_overdue"], 15)
        self.assertEqual(rows[capped.name]["due_date"], getdate("2024-02-19"))
        self.assertEqual(rows[no_terms.name]["due_date"], getdate("2024-02-15"))

        for pi, amount in ((early, 8000), (capped, 4000), (no_terms, 3000)):
            self.assertEqual(flt(rows[pi.name]["outstanding_overdue"]), amount)

    def test_no_written_agreement_limits_to_15_days(self):
        # Same invoice, no written agreement -> 15 days, not 45.
        supplier = MSME_SUPPLIER_WITHOUT_AGREEMENT
        pi = self._pi(supplier, "2024-03-10", 6000, due_date="2024-04-24")

        row = self._run(supplier)[pi.name]

        self.assertEqual(row["due_date"], getdate("2024-03-25"))
        self.assertEqual(flt(row["outstanding_overdue"]), 6000)

    def test_no_credit_terms_falls_back_to_45_days(self):
        # ERPNext defaults due_date to the posting date when no credit terms are
        # set. That is its default, not a same-day agreement, so the 45-day
        # ceiling applies rather than the posting date itself.
        pi = self._pi(self.supplier, "2024-01-01", 3000, due_date="2024-01-01")

        row = self._run(self.supplier)[pi.name]

        self.assertEqual(row["due_date"], getdate("2024-02-15"))
        self.assertEqual(flt(row["outstanding_overdue"]), 3000)


class TestMSME43BHPaymentScenarios(_TestMSME43BHBase):
    """Exercise the same ledger paths ERPNext's payment reconciliation does:
    partial payments, advances, credit/debit notes and Journal Entry payments,
    plus a point-in-time regression against the invoice's authoritative outstanding.
    """

    def test_partial_payments_straddling_due_date(self):
        # PI 10000, due 2023-06-15. Pay 4000 on time, 3000 late (same FY), 3000
        # unpaid at FY-end. Only the unpaid 3000 is disallowed; the 3000 paid
        # late was still paid within the FY, so it is allowed (flagged separately).
        pi = self._pi(self.supplier, "2023-05-01", 10000)
        self._pay(pi, "2023-06-01", amount=4000)  # on time
        self._pay(pi, "2023-08-01", amount=3000)  # late, same FY
        rows = self._run(self.supplier)
        row = rows[pi.name]
        self.assertEqual(flt(row["outstanding"]), 3000)
        self.assertEqual(flt(row["paid_amount"]), 7000)
        self.assertEqual(flt(row["paid_after_due"]), 3000)
        self.assertEqual(flt(row["outstanding_overdue"]), 3000)

    def test_advance_paid_before_invoice_is_on_time(self):
        # Payment dated before the due date (even before the invoice) -> on
        # time -> not in the disallowance statement.
        pi = self._pi(self.supplier, "2023-05-01", 8000)
        self._pay(pi, "2023-05-10")  # well within the 45-day window
        rows = self._run(self.supplier)
        self.assertNotIn(pi.name, rows)

    def test_unadjusted_advance_does_not_reduce_the_disallowance(self):
        # 43B(h) disallows a "sum payable". An advance not yet adjusted against
        # any invoice is an asset, not a sum payable - it has no supply and no
        # 45-day clock, so it cannot reduce the disallowance. It only counts once
        # it is adjusted, at which point it reduces that invoice's outstanding.
        supplier = self._create_msme_supplier(enterprise_type="Micro")
        pi = self._pi(supplier, "2023-05-01", 10000)
        pe = self._make_advance(supplier, pi.credit_to, "2023-06-01", 2000)

        rows = self._run(supplier)

        self.assertEqual(flt(rows[pi.name]["outstanding_overdue"]), 10000)
        self.assertNotIn(pe.name, rows)

    def test_adjusted_advance_reduces_the_disallowance(self):
        # The other side of the same rule: once allocated against the invoice,
        # the payment reduces its outstanding, and the disallowance follows.
        supplier = self._create_msme_supplier(enterprise_type="Micro")
        pi = self._pi(supplier, "2023-05-01", 10000)
        self._pay(pi, "2023-09-01", amount=2000)  # late, but allocated

        row = self._run(supplier)[pi.name]

        self.assertEqual(flt(row["outstanding_overdue"]), 8000)
        self.assertEqual(flt(row["outstanding"]), 8000)

    def test_unreconciled_debit_note_does_not_reduce_the_disallowance(self):
        # A purchase return is a credit, never a sum payable, so it is not
        # disallowable and does not appear in the disallowance statement. Until
        # it is reconciled it does not reduce the invoice's outstanding either -
        # which stays equal to ERPNext's own authoritative figure.
        supplier = self._create_msme_supplier(enterprise_type="Micro")
        pi = self._pi(supplier, "2023-05-01", 10000)
        debit_note = create_purchase_invoice(
            supplier=supplier,
            company=COMPANY,
            posting_date="2023-05-20",
            set_posting_time=1,
            is_return=1,
            return_against=pi.name,
            qty=-1,
            rate=4000,
        )

        rows = self._run(supplier)

        self.assertNotIn(debit_note.name, rows)
        self.assertEqual(
            flt(rows[pi.name]["outstanding"]),
            flt(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount")),
        )
        self.assertEqual(flt(rows[pi.name]["outstanding_overdue"]), 10000)

    def test_journal_entry_payable_excluded(self):
        # 43B(h) disallows sums payable for goods supplied or services rendered
        # (MSMED Act s.15). A JE crediting a supplier is not necessarily a supply
        # - it may be a loan, a reclassification, an opening balance - so it is
        # not a payable for this purpose.
        supplier = self._create_msme_supplier(enterprise_type="Micro")
        sample_pi = self._pi(supplier, "2023-05-01", 100)  # to get accounts
        self._pay(sample_pi, "2023-05-15")

        je = create_journal_entry(
            company=COMPANY,
            posting_date="2023-05-01",
            accounts=[
                {
                    "account": sample_pi.credit_to,
                    "party_type": "Supplier",
                    "party": supplier,
                    "credit_in_account_currency": 5000,
                },
                {
                    "account": self._get_cash_account(),
                    "debit_in_account_currency": 5000,
                },
            ],
        )

        self.assertNotIn(je.name, self._run(supplier))

    def test_disallowance_always_tracks_authoritative_outstanding(self):
        # The compliance guarantee: for an applicable, overdue invoice the
        # disallowable amount is exactly the unpaid outstanding, and that
        # outstanding always equals ERPNext's authoritative Purchase
        # Invoice.outstanding_amount. So whatever a payment / credit note /
        # reconciliation does to outstanding, the disallowance follows it 1:1.
        pi = self._pi(self.supplier, "2023-05-01", 10000)
        self._pay(pi, "2023-09-01", amount=3500)
        row = self._run(self.supplier)[pi.name]
        authoritative = frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount")
        self.assertEqual(flt(row["outstanding"]), flt(authoritative))
        self.assertEqual(flt(row["outstanding_overdue"]), flt(authoritative))

    def test_journal_entry_payment_recognised(self):
        # Pay the invoice via a Journal Entry (creditors debit referencing the PI).
        pi = self._pi(self.supplier, "2023-05-01", 5000)
        create_journal_entry(
            company=COMPANY,
            posting_date="2023-06-01",  # on time
            accounts=[
                {
                    "account": pi.credit_to,
                    "party_type": "Supplier",
                    "party": self.supplier,
                    "debit_in_account_currency": 5000,
                    "reference_type": "Purchase Invoice",
                    "reference_name": pi.name,
                },
                {
                    "account": self._get_cash_account(),
                    "credit_in_account_currency": 5000,
                },
            ],
        )

        # settled in full via JE -> nothing disallowable -> not in the statement
        rows = self._run(self.supplier)
        self.assertNotIn(pi.name, rows)
