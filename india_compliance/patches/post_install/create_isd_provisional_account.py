import frappe

from india_compliance.gst_india.overrides.company import (
    make_default_isd_provisional_account,
)


def execute():
    """Create ISD provisional accounts for all existing Indian companies"""
    company_list = frappe.get_all(
        "Company",
        filters={"country": "India"},
        pluck="name",
        order_by="lft asc",
    )

    for company in company_list:
        try:
            # Skip if account already exists
            if frappe.db.exists(
                "Account",
                {
                    "company": company,
                    "account_name": "ISD Distribution Provisional",
                },
            ):
                continue

            make_default_isd_provisional_account(company)
        except Exception as e:
            frappe.log_error(
                title=f"Failed to create ISD provisional account for {company}",
                message=e,
            )
