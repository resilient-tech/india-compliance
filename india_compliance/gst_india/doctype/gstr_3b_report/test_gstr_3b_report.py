# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import json
import unittest

import frappe
from frappe.utils import getdate

from india_compliance.gst_india.utils.tests import (
    create_purchase_invoice,
    create_sales_invoice,
)


class TestGSTR3BReport(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        filters = {"company": "_Test Indian Registered Company"}

        for doctype in ("Sales Invoice", "Purchase Invoice", "GSTR 3B Report"):
            frappe.db.delete(doctype, filters=filters)

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()

    def test_gstr_3b_report(self):
        month_number_mapping = {
            1: "January",
            2: "February",
            3: "March",
            4: "April",
            5: "May",
            6: "June",
            7: "July",
            8: "August",
            9: "September",
            10: "October",
            11: "November",
            12: "December",
        }

        create_sales_invoices()
        create_purchase_invoices()

        report = frappe.get_doc(
            {
                "doctype": "GSTR 3B Report",
                "company": "_Test Indian Registered Company",
                "company_address": "_Test Indian Registered Company-Billing",
                "year": getdate().year,
                "month": month_number_mapping.get(getdate().month),
            }
        ).insert()

        output = json.loads(report.json_output)
        self.assertEqual(output["sup_details"]["osup_det"]["iamt"], 18)
        self.assertEqual(output["sup_details"]["osup_det"]["txval"], 300)
        self.assertEqual(output["sup_details"]["isup_rev"]["txval"], 100)
        self.assertEqual(output["sup_details"]["isup_rev"]["camt"], 9)
        self.assertEqual(output["itc_elg"]["itc_net"]["samt"], 40)

    def test_gst_rounding(self):
        gst_settings = frappe.get_doc("GST Settings")
        gst_settings.round_off_gst_values = 1
        gst_settings.save()

        si = create_sales_invoice(
            rate=216,
            is_in_state=True,
            do_not_submit=True,
        )

        # Check for 39 instead of 38.88
        self.assertEqual(si.taxes[0].base_tax_amount_after_discount_amount, 19)

        gst_settings.round_off_gst_values = 1
        gst_settings.save()


def create_sales_invoices():
    create_sales_invoice(is_in_state=True)
    create_sales_invoice(item_code="_Test Nil Rated Item")
    create_sales_invoice(
        customer="_Test Registered Composition Customer",
        is_out_state=True,
    )
    create_sales_invoice(
        customer="_Test Unregistered Customer",
        is_in_state=True,
    )


def create_purchase_invoices():
    create_purchase_invoice(is_in_state=True)
    create_purchase_invoice(rate=250, qty=1, is_in_state=True)
    create_purchase_invoice(supplier="_Test Registered Composition Supplier")
    create_purchase_invoice(
        is_in_state_rcm=True,
        supplier="_Test Unregistered Supplier",
        is_reverse_charge=True,
    )
