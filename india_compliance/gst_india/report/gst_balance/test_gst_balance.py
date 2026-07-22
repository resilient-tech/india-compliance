# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, flt, getdate

from india_compliance.gst_india.report.gst_balance.gst_balance import execute
from india_compliance.gst_india.utils import get_gst_accounts_by_type
from india_compliance.gst_india.utils.tests import create_sales_invoice

COMPANY = "_Test Indian Registered Company"


class TestGSTBalance(IntegrationTestCase):
    def setUp(self):
        frappe.db.delete("Sales Invoice", filters={"company": COMPANY})

        self.output_accounts = get_gst_accounts_by_type(COMPANY, "Output")

    def run_report(self, show_summary=0):
        _columns, data = execute(
            frappe._dict(
                company=COMPANY,
                from_date=add_to_date(getdate(), days=-1),
                to_date=getdate(),
                show_summary=show_summary,
            )
        )
        return data

    def closing_balance(self, account):
        """Net closing credit for `account`, or 0 if the report has no row for it."""
        row = next(
            (row for row in self.run_report() if row.get("account") == account),
            None,
        )
        self.assertIsNotNone(row, f"expected a row for {account}")
        return flt(row.get("closing_credit")) - flt(row.get("closing_debit"))

    def test_trial_balance_reports_the_invoice_tax(self):
        cgst_account = self.output_accounts.cgst_account
        before = self.closing_balance(cgst_account)

        create_sales_invoice(is_in_state=1, qty=1, rate=1000)

        self.assertEqual(self.closing_balance(cgst_account) - before, 90)

    def test_summary_mode(self):
        create_sales_invoice(is_in_state=1, qty=1, rate=1000)

        rows = self.run_report(show_summary=1)

        self.assertTrue(rows)
