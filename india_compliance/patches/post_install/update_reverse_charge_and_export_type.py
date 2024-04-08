import frappe

from india_compliance.gst_india.utils.custom_fields import delete_old_fields

DOCTYPES = ("Purchase Invoice", "Sales Invoice")


def execute():
    doctype_columns = {doctype: frappe.db.get_table_columns(doctype) for doctype in DOCTYPES}

    update_field_to_check("reverse_charge", "is_reverse_charge", "Y", doctype_columns)
    update_field_to_check(
        "export_type", "is_export_with_gst", "With Payment of Tax", doctype_columns
    )


def update_field_to_check(old_fieldname, new_fieldname, truthy_value, doctype_columns):
    for doctype, columns in doctype_columns.items():
        # Check for new fieldname, is_export_with_gst is only applicable for Sales Invoice
        if old_fieldname not in columns or new_fieldname not in columns:
            continue

        frappe.db.set_value(doctype, {old_fieldname: truthy_value}, new_fieldname, 1)
        frappe.db.sql_ddl(f"alter table `tab{doctype}` drop column {old_fieldname}")

    delete_old_fields(old_fieldname, DOCTYPES)
