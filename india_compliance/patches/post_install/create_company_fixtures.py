import frappe

from india_compliance.gst_india.overrides.company import (
    create_company_fixtures as create_gst_fixtures,
)
from india_compliance.income_tax_india.overrides.company import (
    create_company_fixtures as create_income_tax_fixtures,
)

"""
This patch is used to create company fixtures for Indian Companies created before installing India Compliance.
"""


def execute():
    company_list = frappe.get_all("Company", filters={"country": "India"}, pluck="name")
    for company in company_list:
        # Income Tax fixtures
        if not frappe.db.exists(
            "Account", {"company": company, "account_name": "TDS Payable"}
        ):
            create_income_tax_fixtures(company)

        # GST fixtures
        if not frappe.db.exists("GST Account", {"company": company}):
            create_gst_fixtures(company)
