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

    values_to_set = {"utgst_account": ""}

    for row in gst_accounts:
        if not row.sgst_account:
            # SGST account was set as not mandatory by user?
            frappe.db.set_value(
                DOCTYPE,
                row.name,
                {"sgst_account": row.utgst_account, **values_to_set},
            )
            return

        frappe.rename_doc(
            "Account",
            row.utgst_account,
            row.sgst_account,
            merge=1,
            force=1,
        )

        frappe.db.set_value(DOCTYPE, row.name, values_to_set)

    click.secho(
        "The UTGST Accounts set in your GST Settings have been merged into the"
        " corresponding SGST / UTGST Accounts.\n",
        fg="yellow",
    )
