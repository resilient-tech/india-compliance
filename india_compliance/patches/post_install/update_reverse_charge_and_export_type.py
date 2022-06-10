import frappe

DOCTYPES = ("Purchase Invoice", "Sales Invoice")


def execute():
    update_and_process_field("reverse_charge", "Y")
    update_and_process_field("export_type", "With Payment of Tax")


def update_and_process_field(field, values_to_update):
    delete_old_fields(field)
    for doctype in DOCTYPES:
        if field not in frappe.db.get_table_columns(doctype):
            continue

        frappe.db.set_value(doctype, {field: values_to_update}, "is_reverse_charge", 1)
        frappe.db.sql_ddl("alter table `tab{0}` drop column {1}".format(doctype, field))


def delete_old_fields(column):
    frappe.db.delete(
        "Custom Field",
        {
            "fieldname": column,
            "dt": ("in", DOCTYPES),
        },
    )
