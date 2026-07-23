# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
import responses
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, getdate

from india_compliance.gst_india.api_classes.base import BASE_URL
from india_compliance.gst_india.report.india_compliance_api_usage.india_compliance_api_usage import (
    execute,
)
from india_compliance.gst_india.utils.e_invoice import generate_e_invoice
from india_compliance.gst_india.utils.test_e_invoice import EInvoiceTestMixin
from india_compliance.gst_india.utils.tests import create_sales_invoice


class TestIndiaComplianceAPIUsage(EInvoiceTestMixin, IntegrationTestCase):
    def run_report(self, report_by):
        _columns, data = execute(
            frappe._dict(
                from_date=getdate(),
                to_date=add_to_date(getdate(), days=1),
                report_by=report_by,
            )
        )
        return data

    @responses.activate
    def test_api_usage_for_generated_e_invoice(self):
        test_data = self.e_invoice_test_data.get("goods_item_with_ewaybill")
        invoice = create_sales_invoice(**test_data.get("kwargs"), qty=1000, is_in_state=True)

        self._mock_e_invoice_response(data=test_data)
        generate_e_invoice(invoice.name)

        request = frappe.get_doc(
            "Integration Request",
            {"reference_doctype": "Sales Invoice", "reference_docname": invoice.name},
        )

        endpoint = request.url.replace(BASE_URL, "")
        row = next(row for row in self.run_report("Endpoint") if row["endpoint"] == endpoint)
        self.assertGreaterEqual(row["api_requests_count"], 1)

        row = next(row for row in self.run_report("Date") if str(row["date"]) == str(getdate()))
        self.assertGreaterEqual(row["api_requests_count"], 1)

        row = next(
            row for row in self.run_report("Linked Document") if row["reference_docname"] == invoice.name
        )
        self.assertEqual(row["reference_doctype"], "Sales Invoice")
        self.assertGreaterEqual(row["api_requests_count"], 1)
