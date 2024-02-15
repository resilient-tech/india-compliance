import frappe

from india_compliance.income_tax_india.overrides.company import (
    set_tax_withholding_category,
)


def execute():
    company = frappe.db.get_value("Global Defaults", None, "default_company")
    set_tax_withholding_category(company)
