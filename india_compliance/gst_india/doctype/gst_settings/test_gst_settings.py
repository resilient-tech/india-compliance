# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import unittest

import frappe


class TestGSTSettings(unittest.TestCase):
    def test_validate_multiple_accounts(self):
        gst_settings_doc = frappe.get_single("GST Settings")

        company = frappe.new_doc("Company")
        company.company_name = "Test Company 1"
        company.abbr = "TC1"
        company.default_currency = "INR"
        company.country = "India"
        company.insert()

        gst_settings_doc.append(
            "gst_accounts",
            {
                "company": company.name,
                "cgst_account": "Input Additional VAT 1% - SMC",
                "sgst_account": "Input Additional VAT 2.5% - SMC",
                "igst_account": "Input Additional VAT 3.75% - SMC",
                "gst_account_type": "Input",
            },
        )

        self.assertRaises(frappe.ValidationError, gst_settings_doc.save)

        company.delete()
