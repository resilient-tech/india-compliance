# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
import re

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils.data import getdate


class TestGSTSettings(FrappeTestCase):

    @change_settings("GST Settings", {"enable_api": 1})
    def test_api_key_enabled(self):
        doc = frappe.get_doc("GST Settings")
        doc.save()

    def test_validate_duplicate_account(self):
        doc = frappe.get_doc("GST Settings")
        doc.append(
            "gst_accounts",
            {
                "company": "_Test Indian Registered Company",
                "account_type": "Input",
                "cgst_account": "Input Tax CGST - _TIRC",
                "sgst_account": "Input Tax SGST - _TIRC",
                "igst_account": "Input Tax IGST - _TIRC",
            },
        )
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Row #\d+: Account .* appears multiple times)"),
            doc.save,
        )
        # Validate Duplicate Account Types for each Company

    def test_validate_duplicate_account_type_for_each_company(self):
        doc = frappe.get_doc("GST Settings")
        for row in doc.gst_accounts:
            if (
                row.company == "_Test Indian Registered Company"
                and row.account_type == "Reverse Charge"
            ):
                row.account_type = "Output"
                self.assertRaisesRegex(
                    frappe.ValidationError,
                    re.compile(
                        r"^(Row #\d+: Account Type .* appears multiple times for .*)"
                    ),
                    doc.save,
                )
                break

    @change_settings(
        "GST Settings",
        {"enable_e_invoice": 1, "apply_e_invoice_only_for_selected_companies": 0},
    )
    def test_validate_e_invoice_applicability_date(self):
        doc = frappe.get_doc("GST Settings")
        doc.enable_e_invoice = 1
        doc.e_invoice_applicable_from = ""
        doc.apply_e_invoice_only_for_selected_companies = 0
        doc.flags.ignore_mandatory = True

        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(.*is mandatory for enabling e-Invoice)"),
            doc.save,
        )

        doc = frappe.get_doc("GST Settings")
        doc.e_invoice_applicable_from = getdate("2020-01-01")

        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(.*date cannot be before.*)"),
            doc.save,
        )

        doc = frappe.get_doc("GST Settings")
        doc.apply_e_invoice_only_for_selected_companies = 1
        company = {
            "company": "_Test Indian Registered Company",
            "applicable_from": getdate("01-04-2024"),
        }
        doc.append("e_invoice_applicable_companies", company)
        doc.save()

    @change_settings("GST Settings", {"enable_api": 1})
    def test_validate_credentials(self):
        doc = frappe.get_doc("GST Settings")
        doc.append(
            "credentials",
            {
                "company": "_Test Indian Registered Company",
                "service": "e-Waybill / e-Invoice",
                "gstin": "24AAQCA8719H1ZC",
                "username": "testing1",
            },
        )
        self.assertRaisesRegex(
            frappe.MandatoryError,
            re.compile(
                r"^(Row #\d+: Password is required when setting a GST Credential"
                " for.*)"
            ),
            doc.save,
        )

        doc = frappe.get_doc("GST Settings")
        doc.append(
            "credentials",
            {
                "company": "_Test Indian Registered Company",
                "service": "Returns",
                "gstin": "24AAQCA8719H1ZC",
                "username": "testing2",
            },
        )
        doc.save()

        doc = frappe.get_doc("GST Settings")
        doc.append(
            "credentials",
            {
                "company": "_Test Indian Registered Company",
                "service": "e-Waybill / e-Invoice",
                "gstin": "24AAQCA8719H1ZC",
                "username": "testing2",
                "password": "TestPass@123",
            },
        )
        doc.save()

    def test_validate_enable_api(self):
        doc = frappe.get_doc("GST Settings")
        doc.enable_api = 1
        frappe.conf.ic_api_secret = None
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(
                r"^(Please counfigure your India Compliance Account to"
                " enable API features)"
            ),
            doc.validate_enable_api,
        )

    @change_settings("GST Settings", {"enable_e_invoice": 1})
    def test_validate_e_invoice_applicable_companies_without_applicable_from(self):
        doc = frappe.get_doc("GST Settings")
        doc.append(
            "e_invoice_applicable_companies",
            {"company": "_Test Indian Registered Company"},
        )
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Row #\d+:.* is mandatory for enabling e-Invoice)"),
            doc.validate_e_invoice_applicable_companies,
        )

    @change_settings("GST Settings", {"enable_e_invoice": 1})
    def test_validate_company_in_e_invoice_applicable_company(self):
        doc = frappe.get_doc("GST Settings")
        doc.apply_e_invoice_only_for_selected_companies = 1
        doc.e_invoice_applicable_companies = []
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(
                r"^(You must select at least one company to which e-Invoice is Applicable)"
            ),
            doc.validate_e_invoice_applicable_companies,
        )

    @change_settings("GST Settings", {"enable_e_invoice": 1})
    def test_validate_e_invoice_applicable_companies_with_applicable_from(self):
        doc = frappe.get_doc("GST Settings")
        doc.append(
            "e_invoice_applicable_companies",
            {
                "company": "_Test Indian Registered Company",
                "applicable_from": "01-01-2024",
            },
        )
        doc.append(
            "e_invoice_applicable_companies",
            {
                "company": "_Test Indian Registered Company",
                "applicable_from": "01-01-2024",
            },
        )
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Row #\d+:.* appears multiple times)"),
            doc.validate_e_invoice_applicable_companies,
        )

    @change_settings("GST Settings", {"enable_e_invoice": 1})
    def test_validate_applicable_from_in_e_invoice(self):
        doc = frappe.get_doc("GST Settings")
        doc.append(
            "e_invoice_applicable_companies",
            {
                "company": "_Test Indian Registered Company",
                "applicable_from": "01-01-2020",
            },
        )
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Row #\d+:.*date cannot be before.*)"),
            doc.validate_e_invoice_applicable_companies,
        )
