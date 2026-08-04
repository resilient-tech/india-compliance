import frappe
from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.overrides.company import (
    GST_SETTINGS_CHILD_TABLES_WITH_COMPANY,
    SINGLE_DOCTYPES_WITH_COMPANY_FIELD,
    get_tax_defaults,
)


<<<<<<< HEAD
class TestCompanyFixtures(FrappeTestCase):
=======
class TestCompany(IntegrationTestCase):
>>>>>>> ab80353f (fix: disable e-Invoice if applicable for only that company)
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_company")

        # company fixtures created here are asserted by the tax defaults tests
        cls.company = cls.create_company("_Test Company", "_TC")

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_company")

    @classmethod
    def create_company(cls, company_name, abbr):
        return frappe.get_doc(
            {
                "doctype": "Company",
                "abbr": abbr,
                "company_name": company_name,
                "country": "India",
                "default_currency": "INR",
                "domain": "Manufacturing",
                "chart_of_accounts": "Standard",
                "enable_perpetual_inventory": 0,
                "gstin": "24AAQCA8719H1ZC",
                "gst_category": "Registered Regular",
            }
        ).insert()

    def test_tax_defaults_setup(self):
        # Check for tax category creations.
        self.assertTrue(frappe.db.exists("Tax Category", "Reverse Charge In-State"))

        for row in get_tax_defaults()["tax_categories"]:
            expected = bool(row.get("is_india_compliance_default"))
            actual = bool(frappe.db.get_value("Tax Category", row["title"], "is_india_compliance_default"))
            self.assertEqual(actual, expected)

    def test_get_tax_defaults(self):
        gst_rate = 12
        default_taxes = get_tax_defaults(gst_rate)

        for template_type in ("sales_tax_templates", "purchase_tax_templates"):
            template = default_taxes["chart_of_accounts"]["*"][template_type]
            for tax in template:
                for row in tax.get("taxes"):
                    expected_rate = (
                        gst_rate if "IGST" in row["account_head"]["account_name"] else gst_rate / 2
                    )
                    self.assertEqual(row["account_head"]["tax_rate"], expected_rate)

<<<<<<< HEAD

class TestCompanyOnTrash(FrappeTestCase):
    def test_company_is_cleared_from_singles(self):
=======
    def test_company_is_cleared_from_gst_settings(self):
>>>>>>> ab80353f (fix: disable e-Invoice if applicable for only that company)
        company = self.create_company("_Test Trash Company", "_TTC")
        other_company = self.create_company("_Test Other Trash Company", "_TOTC")
        gst_settings = self.setup_gst_settings(company, other_company)

        for doctype in SINGLE_DOCTYPES_WITH_COMPANY_FIELD:
            frappe.db.set_single_value(doctype, {"company": company.name, "company_gstin": company.gstin})

        for fieldname in GST_SETTINGS_CHILD_TABLES_WITH_COMPANY:
            self.assertTrue(self.get_gst_settings_rows(gst_settings, fieldname, company.name))
            self.assertTrue(self.get_gst_settings_rows(gst_settings, fieldname, other_company.name))

        company.delete()

        for doctype in SINGLE_DOCTYPES_WITH_COMPANY_FIELD:
            self.assertFalse(frappe.db.get_single_value(doctype, "company"))
            self.assertFalse(frappe.db.get_single_value(doctype, "company_gstin"))

        gst_settings.reload()

        for fieldname in GST_SETTINGS_CHILD_TABLES_WITH_COMPANY:
            self.assertFalse(self.get_gst_settings_rows(gst_settings, fieldname, company.name))
            self.assertTrue(self.get_gst_settings_rows(gst_settings, fieldname, other_company.name))

        # multi company setup: e-Invoice stays enabled while other companies are applicable
        self.assertTrue(gst_settings.enable_e_invoice)

        # deleting the last applicable company disables e-Invoice instead of failing the delete
        other_company.delete()

        gst_settings.reload()
        self.assertFalse(gst_settings.e_invoice_applicable_companies)
        self.assertFalse(gst_settings.enable_e_invoice)
        # left enabled so that re-enabling e-Invoice forces an explicit company selection
        self.assertTrue(gst_settings.apply_e_invoice_only_for_selected_companies)

    def setup_gst_settings(self, *companies):
        """gst_accounts are added by company fixtures, add the remaining tables
        and enable e-Invoice only for the given companies"""
        gst_settings = frappe.get_doc("GST Settings")
        gst_settings.e_invoice_applicable_companies = []

        for company in companies:
            for service in ("e-Waybill / e-Invoice", "Returns"):
                gst_settings.append(
                    "credentials",
                    {
                        "company": company.name,
                        "service": service,
                        "gstin": company.gstin,
                        "username": "test_username",
                        "password": "test_password",
                    },
                )

            gst_settings.append(
                "e_invoice_applicable_companies",
                {"company": company.name, "applicable_from": "2021-04-01"},
            )

        gst_settings.update(
            {
                "api_secret": "test_api_secret",
                "enable_api": 1,
                "enable_e_invoice": 1,
                "apply_e_invoice_only_for_selected_companies": 1,
            }
        )
        gst_settings.save()

        return gst_settings

    def get_gst_settings_rows(self, gst_settings, fieldname, company):
        return [row for row in gst_settings.get(fieldname) if row.company == company]
