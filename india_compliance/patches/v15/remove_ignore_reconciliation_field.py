import frappe

from india_compliance.gst_india.utils.custom_fields import delete_old_fields

DOCTYPES = ("Purchase Invoice", "Bill of Entry")


def execute():
    fieldname = "ignore_reconciliation"

    for doctype in DOCTYPES:
        if fieldname not in frappe.db.get_table_columns(doctype):
            continue

        frappe.db.set_value(doctype, {fieldname: 1}, "reconciliation_status", "Ignored")
        frappe.db.sql_ddl(
            "alter table `tab{0}` drop column {1}".format(doctype, fieldname)
        )

    delete_old_fields(fieldname, DOCTYPES)
