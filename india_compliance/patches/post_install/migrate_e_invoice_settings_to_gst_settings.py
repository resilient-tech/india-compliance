import click

import frappe
from frappe.utils.password import decrypt


def execute():
    singles = frappe.qb.DocType("Singles")
    old_settings = frappe._dict(
        frappe.qb.from_(singles)
        .select(singles.field, singles.value)
        .where(singles.doctype == "E Invoice Settings")
        .where(singles.field.isin(("enable", "applicable_from")))
        .run()
    )

    user = frappe.qb.DocType("E Invoice User")
    auth = frappe.qb.Table("__Auth")
    old_credentials = (
        frappe.qb.from_(user)
        .left_join(auth)
        .on((auth.name == user.name) & (auth.doctype == "E Invoice User"))
        .select(user.company, user.gstin, user.username, auth.password)
        .where(user.parent == "E Invoice Settings")
        .run(as_dict=True)
    )

    for credential in old_credentials:
        credential.password = credential.password and decrypt(credential.password)
        credential.service = "e-Invoice"

    gst_settings = frappe.get_single("GST Settings")
    gst_settings.applicable_from = old_settings.applicable_from
    gst_settings.extend(old_credentials)
    gst_settings.save(ignore_permissions=True)

    if old_settings.enable:
        click.secho(
            "⚠️  Your E Invoice Settings have been migrated to GST Settings."
            " Please enable e-Invoice API in GST Settings manually.",
            fg="yellow",
        )
