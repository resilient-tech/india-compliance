# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import json

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import getdate

from india_compliance.gst_india.utils.tests import (
    create_purchase_invoice,
    create_sales_invoice,
)


class TestGSTR3BReport(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        filters = {"company": "_Test Indian Registered Company"}

        self.maxDiff = None
        for doctype in ("Sales Invoice", "Purchase Invoice", "GSTR 3B Report"):
            frappe.db.delete(doctype, filters=filters)

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
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

        gst_settings = frappe.get_cached_doc("GST Settings")
        gst_settings.round_off_gst_values = 0
        gst_settings.save()

        create_sales_invoices()
        create_purchase_invoices()

        today = getdate()
        ret_period = f"{today.month:02}{today.year}"

        report = frappe.get_doc(
            {
                "doctype": "GSTR 3B Report",
                "company": "_Test Indian Registered Company",
                "company_address": "_Test Indian Registered Company-Billing",
                "year": today.year,
                "month": month_number_mapping.get(today.month),
            }
        ).insert()

        output = json.loads(report.json_output)
        self.assertDictEqual(
            output,
            {
                "gstin": "24AAQCA8719H1ZC",
                "ret_period": ret_period,
                # 3.1
                "sup_details": {
                    "isup_rev": {
                        "camt": 9.0,
                        "csamt": 0.0,
                        "iamt": 0.0,
                        "samt": 9.0,
                        "txval": 100.0,
                    },
                    "osup_det": {
                        "camt": 18.0,
                        "csamt": 0.0,
                        "iamt": 37.98,
                        "samt": 18.0,
                        "txval": 411.0,
                    },
                    "osup_nil_exmp": {"txval": 100.0},
                    "osup_nongst": {"txval": 222.0},
                    "osup_zero": {"csamt": 0.0, "iamt": 99.9, "txval": 999.0},
                },
                # 3.2
                "inter_sup": {
                    "comp_details": [{"iamt": 18.0, "pos": "29", "txval": 100.0}],
                    "uin_details": [],
                    "unreg_details": [{"iamt": 19.98, "pos": "06", "txval": 111.0}],
                },
                # 4
                "itc_elg": {
                    "itc_avl": [
                        {
                            "camt": 0.0,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 0.0,
                            "ty": "IMPG",
                        },
                        {
                            "camt": 0.0,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 0.0,
                            "ty": "IMPS",
                        },
                        {
                            "camt": 9.0,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 9.0,
                            "ty": "ISRC",
                        },
                        {
                            "camt": 0.0,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 0.0,
                            "ty": "ISD",
                        },
                        {
                            "camt": 31.5,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 31.5,
                            "ty": "OTH",
                        },
                    ],
                    "itc_inelg": [
                        {
                            "camt": 0.0,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 0.0,
                            "ty": "RUL",
                        },
                        {
                            "camt": 0.0,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 0.0,
                            "ty": "OTH",
                        },
                    ],
                    "itc_net": {"camt": 40.5, "csamt": 0.0, "iamt": 0.0, "samt": 40.5},
                    "itc_rev": [
                        {
                            "camt": 0.0,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 0.0,
                            "ty": "RUL",
                        },
                        {
                            "camt": 0.0,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 0.0,
                            "ty": "OTH",
                        },
                    ],
                },
                # 5
                "inward_sup": {
                    "isup_details": [
                        {"inter": 100.0, "intra": 0.0, "ty": "GST"},
                        {"inter": 0.0, "intra": 0.0, "ty": "NONGST"},
                    ]
                },
            },
        )

    def test_gst_rounding(self):
        gst_settings = frappe.get_cached_doc("GST Settings")
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
    create_sales_invoice(
        customer="_Test Registered Composition Customer",
        is_out_state=True,
    )
    create_sales_invoice(
        customer="_Test Unregistered Customer",
        is_in_state=True,
    )
    # Unregistered Out of state
    create_sales_invoice(
        customer="_Test Unregistered Customer",
        is_out_state=True,
        place_of_supply="06-Haryana",
        rate=111,
    )

    # Same Item Nil-Rated
    create_sales_invoice(item_tax_template="Nil-Rated - _TIRC")

    # Non Gst item
    create_sales_invoice(item_code="_Test Non GST Item", rate=222)

    # Zero Rated
    create_sales_invoice(
        customer_address="_Test Registered Customer-Billing-1",
        is_export_with_gst=False,
        rate=444,
    )
    create_sales_invoice(
        customer_address="_Test Registered Customer-Billing-1",
        is_export_with_gst=True,
        is_out_state=True,
        rate=555,
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
