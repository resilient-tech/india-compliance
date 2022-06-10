import frappe

DOCTYPES = ("Purchase Invoice", "Sales Invoice")


def execute():
    update_and_process_field("reverse_charge", "is_reverse_charge", "Y")
    update_and_process_field("export_type", "is_export_with_gst", "With Payment of Tax")


def update_and_process_field(old_field, new_field, values_to_update):
    delete_old_fields(old_field)
    for doctype in DOCTYPES:
        if old_field not in frappe.db.get_table_columns(doctype):
            continue

        if new_field in frappe.db.get_table_columns(doctype):
            frappe.db.set_value(doctype, {old_field: values_to_update}, new_field, 1)

        frappe.db.sql_ddl(
            "alter table `tab{0}` drop column {1}".format(doctype, old_field)
        )


def delete_old_fields(column):
    frappe.db.delete(
        "Custom Field",
        {
            "fieldname": column,
            "dt": ("in", DOCTYPES),
        },
    )
