import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from india_compliance.gst_india.constants.custom_fields import REVERSE_CHARGE_FIELD


def execute():
    column = "reverse_charge"

    for doctype in ("Purchase Invoice", "Sales Invoice"):
        if not frappe.db.table_exists(
            doctype
        ) or column not in frappe.db.get_table_columns(doctype):
            continue

        if is_reverse_charge_field_available(doctype):
            frappe.db.set_value(doctype, {column: "Y"}, "is_reverse_charge", 1)

        frappe.db.sql_ddl(
            "alter table `tab{0}` drop column {1}".format(doctype, column)
        )
        frappe.reload_doc("accounts", "doctype", frappe.scrub(doctype), force=True)


def is_reverse_charge_field_available(doctype):
    if doctype == "Sales Invoice":
        return enable_reverse_charge_in_gst_settings(doctype)

    return True


def enable_reverse_charge_in_gst_settings(doctype):
    if not is_reverse_charge_applicable(doctype):
        return

    create_custom_fields(REVERSE_CHARGE_FIELD)
    return frappe.db.set_value("GST Settings", None, "enable_reverse_charge", 1)


def is_reverse_charge_applicable(doctype):
    condition = " where reverse_charge = 'Y'"
    condition += " and docstatus = 1"
    # condition += " and posting_date >= '2019-04-01'"

    return frappe.db.sql(
        "select name from `tab{doctype}` {condition} limit 1".format(
            doctype=doctype, condition=condition
        )
    )
