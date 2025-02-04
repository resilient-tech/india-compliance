# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date

from india_compliance.gst_india.doctype.purchase_reconciliation_tool.test_purchase_reconciliation_tool import (
    create_gst_inward_supply,
)

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


class TestGSTInvoiceManagementSystem(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.gst_ims = frappe.get_doc(
            {
                "doctype": "GST Invoice Management System",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "return_period": "122024",
            }
        )

        default_args = {
            "bill_date": "2024-12-11",
            "return_period_2b": "122024",
            "gen_date_2b": "2024-12-11",
        }

        create_gst_inward_supply(
            **default_args,
            bill_no="BILL-24-00001",
            previous_ims_action="No Action",
        )
        cls.invoice_name_1 = frappe.get_value(
            "GST Inward Supply", {"bill_no": "BILL-24-00001"}
        )

        create_gst_inward_supply(
            **default_args,
            bill_no="BILL-24-00002",
            previous_ims_action="Accepted",
        )
        cls.invoice_name_2 = frappe.get_value(
            "GST Inward Supply", {"bill_no": "BILL-24-00002"}
        )

    def get_periods(self):
        periods = []
        date = add_to_date(None, months=-1)

        for _ in range(10):
            period = date.strftime("%m%Y")

            periods.append(period)
            date = add_to_date(date, months=-1)

        return periods

    def create_gstr_3b_return_log(self, period):
        gstr3b_log = frappe.new_doc("GST Return Log")
        gstr3b_log.return_period = period
        gstr3b_log.company = "_Test Indian Registered Company"
        gstr3b_log.gstin = "24AAQCA8719H1ZC"
        gstr3b_log.return_type = "GSTR3B"
        gstr3b_log.filing_status = "Filed"
        gstr3b_log.insert()
