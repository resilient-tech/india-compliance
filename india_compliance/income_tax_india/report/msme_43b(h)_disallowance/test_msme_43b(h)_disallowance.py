# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt

from india_compliance.gst_india.utils.tests import (
    create_journal_entry,
    create_purchase_invoice,
)
from india_compliance.income_tax_india.utils.test_msme import COMPANY, MSMEReportTestCase

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
        trader = self._create_msme_supplier(enterprise_type="Small", is_trader=1)
        pi = self._pi(trader, "2023-05-01", 9000)
        rows = self._run(trader, "2024-03-31")
        self.assertNotIn(pi.name, rows)

    def test_report_shows_only_disallowable_rows(self):
        # The report is the disallowance statement: unpaid-overdue rows only;
        # paid rows never appear.
        supplier = self._create_msme_supplier(enterprise_type="Micro")
        paid = self._pi(supplier, "2023-05-01", 3000)
        self._pay(paid, "2023-06-01")  # on time
        overdue = self._pi(supplier, "2023-05-01", 7000)

        rows = self._run(supplier, "2024-03-31")
        self.assertNotIn(paid.name, rows)
        self.assertIn(overdue.name, rows)

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
        # No classification row for the invoice's FY = not MSME-registered that
        # year -> the invoice is excluded entirely.
        supplier = frappe.new_doc("Supplier")
        supplier.supplier_name = frappe.generate_hash("MSME", 10)
        supplier.supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0})
        supplier.is_msme_registered = 1
        supplier.udyam_number = "UDYAM-MH-12-3456780"
        supplier.insert()  # no classification row for FY
        pi = self._pi(supplier.name, "2023-05-01", 4000)
        rows = self._run(supplier.name, "2024-03-31")
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

    def test_unreconciled_debit_note_shown_as_unadjusted_credit(self):
        # A standalone return/debit note does NOT net a specific invoice until
        # it is reconciled (matching ERPNext's outstanding_amount), but it DOES
        # reduce what is actually payable to the supplier - so it appears as a
        # negative row and the report total is the net actual disallowance.
        supplier = self._create_msme_supplier(enterprise_type="Micro")
        pi = self._pi(supplier, "2023-05-01", 10000)
        dn = create_purchase_invoice(
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

        invoice_row = rows[pi.name]
        self.assertEqual(flt(invoice_row["outstanding"]), 10000)
        self.assertEqual(
            flt(invoice_row["outstanding"]),
            flt(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount")),
        )

        credit_row = rows[dn.name]
        self.assertEqual(credit_row["payment_status"], "Unadjusted Credit")
        self.assertEqual(flt(credit_row["disallowable_amount"]), -4000)

        # net actual disallowance
        net = sum(flt(row["disallowable_amount"]) for row in rows.values())
        self.assertEqual(net, 6000)

    def test_unadjusted_advance_reduces_net_disallowance(self):
        # An advance paid to the supplier but not yet adjusted against any
        # invoice still reduces the net amount payable.
        supplier = self._create_msme_supplier(enterprise_type="Micro")
        pi = self._pi(supplier, "2023-05-01", 10000)
        pe = self._make_advance(supplier, pi.credit_to, "2023-06-01", 2000)

        rows = self._run(supplier, "2024-03-31")
        self.assertEqual(flt(rows[pi.name]["disallowable_amount"]), 10000)

        advance_row = rows[pe.name]
        self.assertEqual(advance_row["payment_status"], "Unadjusted Advance")
        self.assertEqual(flt(advance_row["disallowable_amount"]), -2000)

    def test_credit_before_from_date_still_nets(self):
        # An unadjusted advance paid BEFORE the report range still reduces the
        # net payable - credits are not range-bound, so the report total
        # reconciles with GL / Accounts Payable.
        supplier = self._create_msme_supplier(enterprise_type="Micro")
        pi = self._pi(supplier, "2023-07-01", 10000)  # within range, overdue
        self._make_advance(supplier, pi.credit_to, "2023-04-10", 2000)

        rows = self._run(supplier, "2024-03-31", from_date="2023-06-01")
        self.assertEqual(flt(rows[pi.name]["disallowable_amount"]), 10000)

        net = sum(flt(row["disallowable_amount"]) for row in rows.values())
        self.assertEqual(net, 8000)

    def test_net_outstanding_matches_accounts_payable_report(self):
        # The consistency guarantee: our net outstanding equals ERPNext's own
        # Accounts Payable report for the same supplier and date - single
        # source of truth (Payment Ledger), provably not drifting.
        from erpnext.accounts.report.accounts_receivable.accounts_receivable import (
            ReceivablePayableReport,
        )

        supplier = self._create_msme_supplier(enterprise_type="Micro")
        pi = self._pi(supplier, "2023-05-01", 10000)  # overdue due
        create_purchase_invoice(  # unreconciled debit note
            supplier=supplier,
            company=COMPANY,
            posting_date="2023-05-20",
            set_posting_time=1,
            is_return=1,
            return_against=pi.name,
            qty=-1,
            rate=4000,
        )
        self._make_advance(supplier, pi.credit_to, "2023-06-01", 2000)

        rows = self._run(supplier, "2024-03-31")
        net_outstanding = sum(flt(row["outstanding"]) for row in rows.values())
        self.assertEqual(net_outstanding, 4000)  # 10000 - 4000 - 2000

        _c, ap_rows, *_rest = ReceivablePayableReport(
            {
                "company": COMPANY,
                "report_date": "2024-03-31",
                "party_type": "Supplier",
                "party": [supplier],
            }
        ).run({"account_type": "Payable", "naming_by": ["Buying Settings", "supp_master_name"]})

        ap_outstanding = sum(flt(row.get("outstanding")) for row in ap_rows)
        self.assertEqual(net_outstanding, ap_outstanding)

    def test_journal_entry_payable_included(self):
        # Payables can arise from vouchers other than Purchase Invoice - a JE
        # crediting the supplier is a sum payable under 43B(h) too.
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

        rows = self._run(supplier, "2024-03-31")
        je_row = rows[je.name]
        self.assertEqual(je_row["voucher_type"], "Journal Entry")
        self.assertEqual(flt(je_row["disallowable_amount"]), 5000)

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

    def test_point_in_time_outstanding_matches_invoice_field(self):
        # Our point-in-time outstanding (as of today) must equal ERPNext's own
        # authoritative Purchase Invoice.outstanding_amount.
        pi = self._pi(self.supplier, "2023-05-01", 9000)
        self._pay(pi, "2023-07-01", amount=5000)
        rows = self._run(self.supplier, frappe.utils.today())
        row = rows[pi.name]
        authoritative = frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount")
        self.assertEqual(flt(row["outstanding"]), flt(authoritative))
