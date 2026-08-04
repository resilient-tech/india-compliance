import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.overrides.company import (
    GST_SETTINGS_CHILD_TABLES_WITH_COMPANY,
    SINGLE_DOCTYPES_WITH_COMPANY_FIELD,
    get_tax_defaults,
)


class TestCompanyFixtures(IntegrationTestCase):
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


class TestCompanyOnTrash(IntegrationTestCase):
    def test_company_is_cleared_from_singles(self):
        company = self.create_company("_Test Trash Company", "_TTC")
        other_company = frappe.get_cached_doc("Company", "_Test Indian Registered Company")

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

        gst_settings = frappe.get_doc("GST Settings")

        for fieldname in GST_SETTINGS_CHILD_TABLES_WITH_COMPANY:
            self.assertFalse(self.get_gst_settings_rows(gst_settings, fieldname, company.name))
            self.assertTrue(self.get_gst_settings_rows(gst_settings, fieldname, other_company.name))

    def create_company(self, company_name, abbr):
        return frappe.get_doc(
            {
                "doctype": "Company",
                "abbr": abbr,
                "company_name": company_name,
                "country": "India",
                "default_currency": "INR",
                "chart_of_accounts": "Standard",
                "gstin": "24AAQCA8719H1ZC",
                "gst_category": "Registered Regular",
            }
        ).insert()

    def setup_gst_settings(self, *companies):
        """gst_accounts are added by company fixtures, add the remaining tables"""
        gst_settings = frappe.get_doc("GST Settings")

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

            if not self.get_gst_settings_rows(gst_settings, "e_invoice_applicable_companies", company.name):
                gst_settings.append(
                    "e_invoice_applicable_companies",
                    {"company": company.name, "applicable_from": "2021-04-01"},
                )

        gst_settings.save()

        return gst_settings

    def get_gst_settings_rows(self, gst_settings, fieldname, company):
        return [row for row in gst_settings.get(fieldname) if row.company == company]
