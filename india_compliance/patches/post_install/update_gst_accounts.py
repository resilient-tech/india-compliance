import click

import frappe


def execute():
    gst_accounts = frappe.get_all(
        "GST Account",
        filters={"parent": "GST Settings", "account_type": ("is", "not set")},
        fields=(
            "name",
            "company",
            "cgst_account",
            "sgst_account",
            "igst_account",
            "is_reverse_charge_account",
        ),
        ignore_ddl=True,
    )

    if not gst_accounts:
        return

    company_wise_account_types = {}
    show_account_type_warning = False

    for row in gst_accounts:
        account_types = company_wise_account_types.setdefault(row.company, [])
        account_type = get_account_type(row)
        if not account_type:
            show_account_type_warning = True
            continue

        if account_type in account_types:
            # TODO: Add a link to the documentation
            click.secho(
                "It seems like you have different GST Accounts for different rates. "
                "This is no longer supported. "
                "Please merge these accounts and manually update GST Settings.\n",
                fg="yellow",
            )
            return

        frappe.db.set_value("GST Account", row.name, "account_type", account_type)
        account_types.append(account_type)

    if show_account_type_warning:
        click.secho(
            "The account type for your GST accounts could not be set automatically. "
            "Please set it manually in GST settings.\n",
            fg="yellow",
        )


def get_account_type(row):
    if row.is_reverse_charge_account:
        return "Reverse Charge"

    accounts = (row.cgst_account, row.sgst_account, row.igst_account)
    if all("input" in (account or "").lower() for account in accounts):
        return "Input"

    if all("output" in (account or "").lower() for account in accounts):
        return "Output"
