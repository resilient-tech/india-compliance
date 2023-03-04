import click

import frappe
from frappe.utils import sbool
from frappe.utils.password import decrypt

from india_compliance.gst_india.constants.custom_fields import E_INVOICE_FIELDS
from india_compliance.gst_india.utils.custom_fields import toggle_custom_fields


def execute():
    singles = frappe.qb.DocType("Singles")
    old_settings = frappe._dict(
        frappe.qb.from_(singles)
        .select(singles.field, singles.value)
        .where(singles.doctype == "E Invoice Settings")
        .where(singles.field.isin(("enable", "applicable_from")))
        .run()
    )

    if not old_settings.applicable_from:
        return

    gst_settings = frappe.get_doc("GST Settings")
    gst_settings.e_invoice_applicable_from = old_settings.applicable_from

    if old_credentials := get_credentials_from_e_invoice_user():
        gst_settings.extend("credentials", old_credentials)
        frappe.db.delete("E Invoice User")

    gst_settings.flags.update(
        ignore_mandatory=True,
        ignore_validate=True,
        ignore_permissions=True,
    )

    gst_settings.save()

    if sbool(old_settings.enable):
        toggle_custom_fields(E_INVOICE_FIELDS, True)
        click.secho(
            (
                "Your e-Invoice Settings have been migrated to GST Settings."
                " Please enable the e-Invoice API in GST Settings manually.\n"
            ),
            fg="yellow",
        )


def get_credentials_from_e_invoice_user():
    if not frappe.db.table_exists("E Invoice User"):
        return

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
        credential.service = "e-Waybill / e-Invoice"

    return old_credentials
