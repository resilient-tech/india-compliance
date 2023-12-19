import frappe
from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.overrides.company import get_tax_defaults


class TestCompanyFixtures(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_company")

        cls.company = frappe.new_doc("Company")
        cls.company.update(
            {
                "abbr": "_TC",
                "company_name": "_Test Company",
                "country": "India",
                "default_currency": "INR",
                "doctype": "Company",
                "domain": "Manufacturing",
                "chart_of_accounts": "Standard",
                "enable_perpetual_inventory": 0,
                "gstin": "24AAQCA8719H1ZC",
                "gst_category": "Registered Regular",
            }
        )
        cls.company.insert()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_company")

    def test_tax_defaults_setup(self):
        # Check for tax category creations.
        self.assertTrue(frappe.db.exists("Tax Category", "Reverse Charge In-State"))

    def test_get_tax_defaults(self):
        gst_rate = 12
        default_taxes = get_tax_defaults(gst_rate)

        for template_type in ("sales_tax_templates", "purchase_tax_templates"):
            template = default_taxes["chart_of_accounts"]["*"][template_type]
            for tax in template:
                for row in tax.get("taxes"):
                    expected_rate = (
                        gst_rate
                        if "IGST" in row["account_head"]["account_name"]
                        else gst_rate / 2
                    )
                    self.assertEqual(row["account_head"]["tax_rate"], expected_rate)
