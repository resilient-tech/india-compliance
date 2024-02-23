import frappe

from india_compliance.income_tax_india.overrides.company import (
    create_or_update_tax_withholding_category,
)


def execute():
    companies = frappe.get_all("Company", filters={"country": "India"}, pluck="name")

    for company in companies:
        create_or_update_tax_withholding_category(company)
