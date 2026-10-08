# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
import responses
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from india_compliance.gst_india.report.e_invoice_summary.e_invoice_summary import execute
from india_compliance.gst_india.utils.e_invoice import generate_e_invoice
from india_compliance.gst_india.utils.test_e_invoice import EInvoiceTestMixin
from india_compliance.gst_india.utils.tests import create_sales_invoice


class TestEInvoiceSummary(EInvoiceTestMixin, IntegrationTestCase):
    def run_report(self, **filters):
        _columns, data = execute(
            frappe._dict(
                company="_Test Indian Registered Company",
                from_date=getdate(),
                to_date=getdate(),
                **filters,
            )
        )
        return data

    @responses.activate
    def test_generated_invoice_is_reported_with_its_log(self):
        test_data = self.e_invoice_test_data.get("goods_item_with_ewaybill")
        invoice = create_sales_invoice(**test_data.get("kwargs"), qty=1000, is_in_state=True)

        self._mock_e_invoice_response(data=test_data)
        generate_e_invoice(invoice.name)

        row = next(row for row in self.run_report() if row["sales_invoice"] == invoice.name)

        result = test_data.get("response_data").get("result")
        self.assertEqual(row["einvoice_status"], "Generated")
        self.assertEqual(row["irn"], result.get("Irn"))
        self.assertEqual(row["docstatus"], "Submitted")
        self.assertEqual(row["is_return"], "N")
        # comes from the joined e-Invoice Log
        self.assertEqual(row["acknowledgement_number"], str(result.get("AckNo")))

    @responses.activate
    def test_status_filter(self):
        test_data = self.e_invoice_test_data.get("goods_item_with_ewaybill")
        invoice = create_sales_invoice(**test_data.get("kwargs"), qty=1000, is_in_state=True)

        self._mock_e_invoice_response(data=test_data)
        generate_e_invoice(invoice.name)

        rows = self.run_report(status="Generated")
        self.assertIn(invoice.name, {row["sales_invoice"] for row in rows})
        self.assertEqual({"Generated"}, {row["einvoice_status"] for row in rows})

        # the site may hold other cancelled invoices; this one must not be among them
        cancelled = self.run_report(status="Cancelled")
        self.assertNotIn(invoice.name, {row["sales_invoice"] for row in cancelled})
        self.assertLessEqual({row["einvoice_status"] for row in cancelled}, {"Cancelled"})
