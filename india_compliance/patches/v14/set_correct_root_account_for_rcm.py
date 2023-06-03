import frappe

from india_compliance.gst_india.constants import GST_ACCOUNT_FIELDS


def execute():
    settings = frappe.get_doc("GST Settings")
    company_accounts = get_company_accounts(settings)

    for accounts in company_accounts.values():
        if not accounts.get("Output") or not accounts.get("Reverse Charge"):
            continue

        rcm_accounts = get_asset_rcm_accounts(accounts)
        if not rcm_accounts:
            continue

        output_account = frappe.db.get_value(
            "Account",
            accounts["Output"].cgst_account,
            ["parent_account", "root_type"],
            as_dict=True,
        )

        if not output_account:
            continue

        # update reverse charge accounts
        frappe.db.set_value(
            "Account",
            {"name": ("in", rcm_accounts)},
            output_account,
            update_modified=False,
        )


def get_company_accounts(settings):
    company_accounts = {}
    for row in settings.gst_accounts:
        company_accounts.setdefault(row.company, {})
        company_accounts[row.company][row.account_type] = row

    return company_accounts


def get_asset_rcm_accounts(accounts):
    return frappe.get_all(
        "Account",
        filters={
            "root_type": "Asset",
            "name": (
                "in",
                [accounts["Reverse Charge"].get(field) for field in GST_ACCOUNT_FIELDS],
            ),
        },
        pluck="name",
    )
