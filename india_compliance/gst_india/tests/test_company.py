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

        total_company_gst_accounts = frappe.db.count(
            "GST Account", {"parent": "GST Settings", "company": company}
        )

        self.assertEqual(total_company_gst_accounts, 3)
