# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt

from india_compliance.gst_india.utils.tests import (
    create_journal_entry,
    create_purchase_invoice,
)
from india_compliance.income_tax_india.utils.test_msme_utils import COMPANY, MSMEReportTestCase

# this folder has parentheses in its name, which plain `import` syntax cannot
# express - resolve the report module through frappe instead
REPORT_PATH = "india_compliance.income_tax_india.report.msme_43b(h)_disallowance.msme_43b(h)_disallowance"


class _TestMSME43BHBase(MSMEReportTestCase):
    def _run(self, supplier, as_on_date, **extra_filters):
        execute = frappe.get_attr(f"{REPORT_PATH}.execute")
        _columns, data = execute(
            {
                "company": COMPANY,
                # FY 2023-2024 date bounds
                "from_date": "2023-04-01",
                "to_date": "2024-03-31",
                "as_on_date": as_on_date,
                "supplier": supplier,
                **extra_filters,
            }
        )
        return {row["voucher_no"]: row for row in data}

    def _count_queries(self, supplier, as_on_date):
        queries = []
        original = frappe.db.sql

        def spy(*args, **kwargs):
            queries.append(1)
            return original(*args, **kwargs)

        frappe.db.sql = spy
        try:
            self._run(supplier, as_on_date)
        finally:
            frappe.db.sql = original

        return len(queries)


class TestMSME43BHPerformance(_TestMSME43BHBase):
    def test_query_count_does_not_grow_with_rows(self):
        """The MSME pipeline is bulk-loaded: more invoices must not mean more queries."""
        supplier = self._create_msme_supplier(enterprise_type="Micro")

        for _ in range(3):
            self._pi(supplier, "2023-05-01", 1000)

        few = self._count_queries(supplier, "2024-03-31")

        for _ in range(12):
            self._pi(supplier, "2023-05-01", 1000)

        many = self._count_queries(supplier, "2024-03-31")

        self.assertEqual(len(self._run(supplier, "2024-03-31")), 15)
        self.assertEqual(few, many, "query count scales with row count - an N+1 has crept in")


class TestMSME43BHReport(_TestMSME43BHBase):
    def test_unpaid_overdue_is_disallowed(self):
        # Posted 2023-05-01 -> due 2023-06-15. Unpaid as on 2024-03-31 -> disallowed.
        pi = self._pi(self.supplier, "2023-05-01", 10000)
        rows = self._run(self.supplier, "2024-03-31")
        row = rows[pi.name]
        self.assertEqual(row["payment_status"], "Unpaid - Overdue")
        self.assertEqual(flt(row["disallowable_amount"]), 10000)
        self.assertEqual(flt(row["outstanding"]), 10000)

    def test_paid_late_within_fy_is_allowed_not_disallowed(self):
        # Due 2023-06-15, paid 2023-08-01 (late but WITHIN FY 2023-24). 43B(h)
        # allows the deduction in the year of actual payment = same FY, so it
        # is NOT disallowed and does not appear in the disallowance statement
        # (visible in Form-1's invoice-wise view instead).
        pi = self._pi(self.supplier, "2023-05-01", 5000)
        self._pay(pi, "2023-08-01")
        rows = self._run(self.supplier, "2024-03-31")
        self.assertNotIn(pi.name, rows)

    def test_unpaid_at_year_end_disallowed_even_if_paid_next_fy(self):
        # Due 2023-06-15, still unpaid at FY-end 2024-03-31 -> disallowed in
        # 2023-24. The later-FY payment does not change FY 2023-24's add-back.
        pi = self._pi(self.supplier, "2023-05-01", 7000)
        self._pay(pi, "2024-05-01")  # paid in FY 2024-25, after the FY-end
        rows = self._run(self.supplier, "2024-03-31")
        row = rows[pi.name]
        self.assertEqual(flt(row["outstanding"]), 7000)
        self.assertEqual(flt(row["disallowable_amount"]), 7000)

    def test_paid_on_time_not_disallowed(self):
        # Due 2023-06-15, paid 2023-06-01 (on time) -> not in the statement.
        pi = self._pi(self.supplier, "2023-05-01", 3000)
        self._pay(pi, "2023-06-01")
        rows = self._run(self.supplier, "2024-03-31")
        self.assertNotIn(pi.name, rows)

    def test_medium_supplier_excluded(self):
        medium = self._create_msme_supplier(enterprise_type="Medium")
        pi = self._pi(medium, "2023-05-01", 9000)
        rows = self._run(medium, "2024-03-31")
        # Medium is not 43B(h)-applicable -> no rows.
        self.assertNotIn(pi.name, rows)

    def test_trader_excluded(self):
        trader = self._create_msme_supplier(enterprise_type="Small", activity="Trading")
        pi = self._pi(trader, "2023-05-01", 9000)
        rows = self._run(trader, "2024-03-31")
        self.assertNotIn(pi.name, rows)

    def test_enterprise_type_filter_narrows_within_applicable(self):
        # The type filter narrows Micro vs Small; it never widens the report
        # past 43B(h) applicability (a Medium filter shows nothing).
        medium = self._create_msme_supplier(enterprise_type="Medium")
        self._pi(medium, "2023-05-01", 9000)
        self.assertEqual(self._run(medium, "2024-03-31", enterprise_type="Medium"), {})

        micro_pi = self._pi(self.supplier, "2023-05-01", 6000)
        rows = self._run(self.supplier, "2024-03-31", enterprise_type="Micro")
        self.assertIn(micro_pi.name, rows)
        self.assertTrue(all(row["enterprise_type"] == "Micro" for row in rows.values()))

    def test_unclassified_supplier_excluded(self):
        # Registered, but with no classification row for the invoice's FY = not
        # MSME that year -> the invoice is excluded entirely.
        supplier = self._create_msme_supplier(enterprise_type="Micro", financial_year="2024-2025")
        pi = self._pi(supplier, "2023-05-01", 4000)
        rows = self._run(supplier, "2024-03-31")
        self.assertNotIn(pi.name, rows)


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
        rows = self._run(self.supplier, "2024-03-31")
        row = rows[pi.name]
        self.assertEqual(flt(row["outstanding"]), 3000)
        self.assertEqual(flt(row["paid_amount"]), 7000)
        self.assertEqual(flt(row["paid_after_due"]), 3000)
        self.assertEqual(flt(row["disallowable_amount"]), 3000)

    def test_advance_paid_before_invoice_is_on_time(self):
        # Payment dated before the due date (even before the invoice) -> on
        # time -> not in the disallowance statement.
        pi = self._pi(self.supplier, "2023-05-01", 8000)
        self._pay(pi, "2023-05-10")  # well within the 45-day window
        rows = self._run(self.supplier, "2024-03-31")
        self.assertNotIn(pi.name, rows)

    def test_unadjusted_advance_does_not_reduce_the_disallowance(self):
        # 43B(h) disallows a "sum payable". An advance not yet adjusted against
        # any invoice is an asset, not a sum payable - it has no supply and no
        # 45-day clock, so it cannot reduce the disallowance. It only counts once
        # it is adjusted, at which point it reduces that invoice's outstanding.
        supplier = self._create_msme_supplier(enterprise_type="Micro")
        pi = self._pi(supplier, "2023-05-01", 10000)
        pe = self._make_advance(supplier, pi.credit_to, "2023-06-01", 2000)

        rows = self._run(supplier, "2024-03-31")

        self.assertEqual(flt(rows[pi.name]["disallowable_amount"]), 10000)
        self.assertNotIn(pe.name, rows)

    def test_adjusted_advance_reduces_the_disallowance(self):
        # The other side of the same rule: once allocated against the invoice,
        # the payment reduces its outstanding, and the disallowance follows.
        supplier = self._create_msme_supplier(enterprise_type="Micro")
        pi = self._pi(supplier, "2023-05-01", 10000)
        self._pay(pi, "2023-09-01", amount=2000)  # late, but allocated

        row = self._run(supplier, "2024-03-31")[pi.name]

        self.assertEqual(flt(row["disallowable_amount"]), 8000)
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

        rows = self._run(supplier, "2024-03-31")

        self.assertNotIn(debit_note.name, rows)
        self.assertEqual(
            flt(rows[pi.name]["outstanding"]),
            flt(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount")),
        )
        self.assertEqual(flt(rows[pi.name]["disallowable_amount"]), 10000)

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

        self.assertNotIn(je.name, self._run(supplier, "2024-03-31"))

    def test_disallowance_always_tracks_authoritative_outstanding(self):
        # The compliance guarantee: for an applicable, overdue invoice the
        # disallowable amount is exactly the unpaid outstanding, and that
        # outstanding always equals ERPNext's authoritative Purchase
        # Invoice.outstanding_amount. So whatever a payment / credit note /
        # reconciliation does to outstanding, the disallowance follows it 1:1.
        pi = self._pi(self.supplier, "2023-05-01", 10000)
        self._pay(pi, "2023-09-01", amount=3500)
        row = self._run(self.supplier, "2024-03-31")[pi.name]
        authoritative = frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount")
        self.assertEqual(flt(row["outstanding"]), flt(authoritative))
        self.assertEqual(flt(row["disallowable_amount"]), flt(authoritative))

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
        rows = self._run(self.supplier, "2024-03-31")
        self.assertNotIn(pi.name, rows)
