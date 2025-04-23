# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.tests import IntegrationTestCase, change_settings

from india_compliance.gst_india.report.hsn_wise_summary_of_outward_supplies.hsn_wise_summary_of_outward_supplies import (
    execute as run_report,
)
from india_compliance.gst_india.report.hsn_wise_summary_of_outward_supplies.hsn_wise_summary_of_outward_supplies import (
    get_hsn_wise_json_data,
)
from india_compliance.gst_india.utils.tests import append_item, create_sales_invoice


class TestHSNWiseSummaryReport(IntegrationTestCase):
    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()

    def test_hsn_summary_for_invoice_with_duplicate_items(self):
        si_one = create_sales_invoice(
            do_not_save=1, is_in_state=True, gst_hsn_code="61149090"
        )
        append_item(si_one, frappe._dict(gst_hsn_code="61149090", uom="Box"))
        append_item(si_one, frappe._dict(gst_hsn_code="61149090", uom="Litre"))
        si_one.submit()

        si_two = create_sales_invoice(
            do_not_save=1, is_in_state=True, gst_hsn_code="61149090"
        )
        append_item(si_two, frappe._dict(gst_hsn_code="61149090", uom="Box"))
        append_item(si_two, frappe._dict(gst_hsn_code="61149090", uom="Litre"))

        si_two.submit()

        _, data = run_report(
            filters=frappe._dict(
                {
                    "company": "_Test Indian Registered Company",
                    "company_gstin": si_one.company_gstin,
                    "from_date": si_one.posting_date,
                    "to_date": si_one.posting_date,
                }
            )
        )

        filtered_rows = [row for row in data if row["hsn_code"] == "61149090"]
        self.assertTrue(filtered_rows)

        hsn_row = filtered_rows[0]
        self.assertEqual(hsn_row["quantity"], 2.0)
        self.assertEqual(hsn_row["total_taxable_value"], 200)
        self.assertEqual(hsn_row["document_value"], 236)  # 2 * 1.18 * 100

    @change_settings("GST Settings", {"validate_hsn_code": 0})
    def test_json_upload_for_missing_hsn_code(self):
        frappe.db.set_value(
            "Item", "_Test Trading Goods 1", "gst_hsn_code", ""
        )  # Avoid fetching of hsn code from item
        si = create_sales_invoice()

        filters = frappe._dict(
            {
                "company": "_Test Indian Registered Company",
                "company_gstin": si.company_gstin,
                "from_date": si.posting_date,
                "to_date": si.posting_date,
            }
        )

        _, data = run_report(filters)

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(GST HSN Code is missing in one or more invoices*)"),
            get_hsn_wise_json_data,
            report_data=data,
            filters=filters,
        )
