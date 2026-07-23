# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from india_compliance.gst_india.report.gst_tax_rate_wise_summary.gst_tax_rate_wise_summary import (
    execute,
)
from india_compliance.gst_india.utils.tests import create_purchase_invoice, create_sales_invoice

COMPANY = "_Test Indian Registered Company"


class TestGSTTaxRateWiseSummary(IntegrationTestCase):
    """One row per tax rate, aggregated over the vouchers of the period."""

    def setUp(self):
        for doctype in ("Sales Invoice", "Purchase Invoice"):
            frappe.db.delete(doctype, filters={"company": COMPANY})

    def run_report(self, voucher_type):
        _columns, data = execute(
            frappe._dict(
                company=COMPANY,
                date_range=[getdate(), getdate()],
                voucher_type=voucher_type,
            )
        )
        return data

    def test_sales_invoice_grouped_by_rate(self):
        create_sales_invoice(is_in_state=1, qty=1, rate=1000)

        rows = self.run_report("Sales Invoice")

        self.assertTrue(rows, "expected a row for the invoice just raised")
        row = next(row for row in rows if row.get("tax_rate") == 18.0)
        self.assertEqual(row["taxable_value"], 1000)
        self.assertEqual(row["cgst_amount"], 90)
        self.assertEqual(row["sgst_amount"], 90)

    def test_purchase_invoice_grouped_by_rate(self):
        create_purchase_invoice(is_in_state=1, qty=1, rate=1000)

        rows = self.run_report("Purchase Invoice")

        row = next(row for row in rows if row.get("tax_rate") == 18.0)
        self.assertEqual(row["taxable_value"], 1000)
