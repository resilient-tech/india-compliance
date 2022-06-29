import click

import frappe

DOCTYPE = "GST Account"


def execute():
    if not frappe.db.has_column(DOCTYPE, "utgst_account"):
        return

    gst_accounts = frappe.get_all(
        DOCTYPE,
        filters={"parent": "GST Settings", "utgst_account": ("is", "set")},
        fields=(
            "name",
            "sgst_account",
            "utgst_account",
        ),
    )

    if not gst_accounts:
        return

    for row in gst_accounts:
        # SGST account was set as not mandatory by user?
        if not row.sgst_account:
            frappe.db.set_value(DOCTYPE, row.name, "sgst_account", row.utgst_account)
            continue

        frappe.rename_doc(
            "Account",
            row.utgst_account,
            row.sgst_account,
            merge=1,
            force=1,
        )

    click.secho(
        "The UTGST Accounts set in your GST Settings have been merged into the"
        " corresponding SGST / UTGST Accounts.\n",
        fg="yellow",
    )
