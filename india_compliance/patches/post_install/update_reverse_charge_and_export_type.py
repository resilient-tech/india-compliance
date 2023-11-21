import frappe

from india_compliance.gst_india.utils.custom_fields import delete_old_fields

DOCTYPES = ("Purchase Invoice", "Sales Invoice")

DOCTYPE_COLUMNS = {
    doctype: frappe.db.get_table_columns(doctype) for doctype in DOCTYPES
}


def execute():
    update_field_to_check("reverse_charge", "is_reverse_charge", "Y")
    update_field_to_check("export_type", "is_export_with_gst", "With Payment of Tax")


def update_field_to_check(old_fieldname, new_fieldname, truthy_value):
    for doctype, columns in DOCTYPE_COLUMNS.items():
        # Check for new fieldname, is_export_with_gst is only applicable for Sales Invoice
        if old_fieldname not in columns or new_fieldname not in columns:
            continue

        frappe.db.set_value(doctype, {old_fieldname: truthy_value}, new_fieldname, 1)
        frappe.db.sql_ddl(
            "alter table `tab{0}` drop column {1}".format(doctype, old_fieldname)
        )

    delete_old_fields(old_fieldname, DOCTYPES)
