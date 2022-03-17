import unittest

import frappe

from india_compliance.gst_india.overrides.company import make_default_tax_templates


class TestCompanyUtility(unittest.TestCase):
    def test_make_default_tax_templates(self):
        company = "Test Case"
        country = "India"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Company {0} does not exist yet. Taxes setup aborted.".format(company),
            make_default_tax_templates,
            company=company,
            country=country,
        )

        company = "_Test Company"
        make_default_tax_templates(company=company, country=country)

        expected_result = [
            {
                "cgst_account": "Input Tax CGST - _TC",
                "sgst_account": "Input Tax SGST - _TC",
                "igst_account": "Input Tax IGST - _TC",
                "account_type": "Input",
            },
            {
                "cgst_account": "Output Tax CGST - _TC",
                "sgst_account": "Output Tax SGST - _TC",
                "igst_account": "Output Tax IGST - _TC",
                "account_type": "Output",
            },
            {
                "cgst_account": "Input Tax CGST RCM - _TC",
                "sgst_account": "Input Tax SGST RCM - _TC",
                "igst_account": "Input Tax IGST RCM - _TC",
                "account_type": "Reverse Charge",
            },
        ]

        company_gst_account = frappe.db.get_all(
            "GST Account",
            {"parent": "GST Settings", "company": company},
            ["cgst_account", "sgst_account", "igst_account", "account_type"],
        )
        self.assertEqual(company_gst_account, expected_result)
