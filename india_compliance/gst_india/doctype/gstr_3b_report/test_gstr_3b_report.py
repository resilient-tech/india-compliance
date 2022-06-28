# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import json
import unittest

import frappe
from frappe.utils import getdate

from india_compliance.tests.utils import create_purchase_invoice, create_sales_invoice

test_dependencies = ["Territory", "Customer Group", "Supplier Group", "Item"]


class TestGSTR3BReport(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")

        frappe.db.sql(
            "delete from `tabSales Invoice` where company='_Test Company GST'"
        )
        frappe.db.sql(
            "delete from `tabPurchase Invoice` where company='_Test Company GST'"
        )
        frappe.db.sql(
            "delete from `tabGSTR 3B Report` where company='_Test Company GST'"
        )

        get_item(properties={"is_nil_exempt": 1})
        set_account_heads()

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

        make_sales_invoice()
        create_purchase_invoices()

        if frappe.db.exists(
            "GSTR 3B Report",
            "GSTR3B-March-2019-_Test Indian Registered Company-Billing",
        ):
            report = frappe.get_doc(
                "GSTR 3B Report",
                "GSTR3B-March-2019-_Test Indian Registered Company-Billing",
            )
            report.save()
        else:
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

        self.assertEqual(output["sup_details"]["osup_det"]["iamt"], 54)
        self.assertEqual(output["inter_sup"]["unreg_details"][0]["iamt"], 18),
        self.assertEqual(output["sup_details"]["osup_nil_exmp"]["txval"], 100),
        self.assertEqual(output["inward_sup"]["isup_details"][0]["intra"], 250)
        self.assertEqual(output["itc_elg"]["itc_avl"][4]["samt"], 22.50)
        self.assertEqual(output["itc_elg"]["itc_avl"][4]["camt"], 22.50)

    def test_gst_rounding(self):
        gst_settings = frappe.get_doc("GST Settings")
        gst_settings.round_off_gst_values = 1
        gst_settings.save()

        current_country = frappe.flags.country
        frappe.flags.country = "India"

        si = create_sales_invoice(
            rate=216,
            taxes="out-of-state",
            do_not_submit=True,
        )

        # Check for 39 instead of 38.88
        self.assertEqual(si.taxes[0].base_tax_amount_after_discount_amount, 39)

        frappe.flags.country = current_country
        gst_settings.round_off_gst_values = 1
        gst_settings.save()

    def test_gst_category_auto_update(self):
        customer = frappe.get_doc("Customer", "_Test Unregistered Customer")
        self.assertEqual(customer.gst_category, "Unregistered")

        if not frappe.db.exists("Address", "_Test Unregistered Customer-Billing"):
            frappe.get_doc(
                {
                    "address_line1": "Test Address - 8",
                    "address_type": "Billing",
                    "city": "_Test City",
                    "state": "Karnataka",
                    "country": "India",
                    "doctype": "Address",
                    "is_primary_address": 1,
                    "gstin": "29AZWPS7135H1ZG",
                    "links": [
                        {
                            "link_doctype": "Customer",
                            "link_name": "_Test Unregistered Customer",
                        }
                    ],
                }
            ).insert()

        customer.load_from_db()
        self.assertEqual(customer.gst_category, "Registered Regular")

        frappe.delete_doc("Address", "_Test Unregistered Customer-Billing")
        customer.load_from_db()
        self.assertEqual(customer.gst_category, "Unregistered")


def make_sales_invoice():
    create_sales_invoice(taxes="out-of-state")

    create_sales_invoice(
        customer="_Test Registered Composition Customer", taxes="out-of-state"
    )

    create_sales_invoice(customer="_Test Unregistered Customer", taxes="out-of-state")

    create_sales_invoice(
        customer="_Test Registered Customer", item="_Test Trading Goods 1"
    )


def create_purchase_invoices():
    create_purchase_invoice(taxes="in-state")

    pi1 = create_purchase_invoice(
        item="_Test Trading Goods 1",
        do_not_save=1,
    )

    pi1.shipping_address = "_Test Registered Supplier-Billing"
    pi1.save()
    pi1.submit()

    create_purchase_invoice(item="_Test Trading Goods 1", rate=250, qty=1)


def get_item(properties=None):
    if not properties:
        return

    item = frappe.get_doc("Item", "_Test Trading Goods 1")
    item.update(properties)
    item.save()


def set_account_heads():
    gst_settings = frappe.get_doc("GST Settings")

    gst_account = frappe.get_all(
        "GST Account",
        fields=["cgst_account", "sgst_account", "igst_account"],
        filters={"company": "_Test Indian Registered Company"},
    )

    if not gst_account:
        gst_settings.append(
            "gst_accounts",
            {
                "company": "_Test Indian Registered Company",
                "cgst_account": "Output Tax CGST - _GST",
                "sgst_account": "Output Tax SGST - _GST",
                "igst_account": "Output Tax IGST - _GST",
            },
        )

        gst_settings.save()
