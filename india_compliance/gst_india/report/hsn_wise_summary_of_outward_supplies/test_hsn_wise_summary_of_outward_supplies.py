# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


from unittest import TestCase

import frappe

from india_compliance.gst_india.report.hsn_wise_summary_of_outward_supplies.hsn_wise_summary_of_outward_supplies import (
    execute as run_report,
)
from india_compliance.gst_india.testutils import append_items, create_sales_invoice


class TestHSNWiseSummaryReport(TestCase):
    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()

    def test_hsn_summary_for_invoice_with_duplicate_items(self):
        si = create_sales_invoice(do_not_save=1, is_in_state=True)
        append_items(si, frappe._dict())

        si.submit()
        si.reload()

        [columns, data] = run_report(
            filters=frappe._dict(
                {
                    "company": "_Test Indian Registered Company",
                    "company_gstin": si.company_gstin,
                    "from_date": si.posting_date,
                    "to_date": si.posting_date,
                }
            )
        )

        filtered_rows = list(
            filter(lambda row: row["gst_hsn_code"] == "61149090", data)
        )
        self.assertTrue(filtered_rows)

        hsn_row = filtered_rows[0]
        self.assertEquals(hsn_row["stock_qty"], 4.0)
        self.assertEquals(hsn_row["total_amount"], 436)
