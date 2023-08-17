import frappe
from frappe.tests.utils import FrappeTestCase


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
