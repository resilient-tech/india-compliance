import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.income_tax_india.overrides.company import (
    TDS_ACCOUNT_NAME,
    create_or_update_tax_withholding_category,
    create_tds_account,
)


class TestCompanyOverride(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_income_tax_company")

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_income_tax_company")

    def test_tds_payable_account_is_linked_in_tax_withholding_category(self):
        company = "_Test Indian Registered Company"

        create_tds_account(company)
        tds_account = frappe.db.get_value(
            "Account",
            {"account_name": TDS_ACCOUNT_NAME, "company": company, "is_group": 0},
            "name",
        )
        self.assertTrue(tds_account)

        create_or_update_tax_withholding_category(company)

        linked = False
        for category in frappe.get_all("Tax Withholding Category", pluck="name"):
            category_doc = frappe.get_doc("Tax Withholding Category", category)
            if any(row.company == company and row.account == tds_account for row in category_doc.accounts):
                linked = True
                break

        self.assertTrue(linked)
