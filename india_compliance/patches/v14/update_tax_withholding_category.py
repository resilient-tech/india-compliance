import frappe

from india_compliance.income_tax_india.overrides.company import (
    set_tax_withholding_category,
)


def execute():
    companies = frappe.get_all("Company", filters={"country": "India"}, pluck="name")

    for company in companies:
        set_tax_withholding_category(company)
