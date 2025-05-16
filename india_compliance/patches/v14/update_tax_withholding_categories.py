import frappe

from india_compliance.income_tax_india.overrides.company import (
    create_or_update_tax_withholding_category,
)


def execute():
    company_list = frappe.get_all(
        "Company", filters={"country": "India"}, pluck="name", order_by="lft asc"
    )

    for company in company_list:
        create_or_update_tax_withholding_category(company)
