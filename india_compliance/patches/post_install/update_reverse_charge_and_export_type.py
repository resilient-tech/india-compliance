import frappe

from india_compliance.gst_india.utils import delete_old_fields

DOCTYPES = ("Purchase Invoice", "Sales Invoice")


def execute():
    update_field_to_check("reverse_charge", "is_reverse_charge", "Y")
    update_field_to_check("export_type", "is_export_with_gst", "With Payment of Tax")


def update_field_to_check(old_fieldname, new_fieldname, truthy_value):
    for doctype in DOCTYPES:
        doc_columns = frappe.db.get_table_columns(doctype)
        if old_fieldname not in doc_columns or new_fieldname not in doc_columns:
            continue

        frappe.db.set_value(doctype, {old_fieldname: truthy_value}, new_fieldname, 1)
        frappe.db.sql_ddl(
            "alter table `tab{0}` drop column {1}".format(doctype, old_fieldname)
        )

    delete_old_fields(old_fieldname, DOCTYPES)
