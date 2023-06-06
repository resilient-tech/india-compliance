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
            update_root_for_rcm(company)
            create_gst_fixtures(company)


def update_root_for_rcm(company):
    # Root type for RCM had been updated to "Liability".
    # This will ensure DuplicateEntryError is not raised for RCM accounts.

    # Hardcoded for exact account names only
    rcm_accounts = frappe.get_all(
        "Account",
        filters={
            "root_type": "Asset",
            "name": ("like", "Input Tax %GST RCM%"),
            "company": company,
        },
        pluck="name",
    )

    if not rcm_accounts:
        return

    output_account = frappe.db.get_value(
        "Account",
        {"name": ("like", "Output Tax %GST%"), "company": company},
        ["parent_account", "root_type"],
        as_dict=True,
    )

    if not output_account:
        abbr = frappe.db.get_value("Company", company, "abbr")
        output_account = {
            "parent_account": f"Duties and Taxes - {abbr}",
            "root_type": "Liability",
        }

    # update reverse charge accounts
    frappe.db.set_value(
        "Account",
        {"name": ("in", rcm_accounts)},
        output_account,
        update_modified=False,
    )
