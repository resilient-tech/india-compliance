import frappe


def execute():
    update_and_process_column(
        column="reverse_charge",
        doctypes=("Purchase Invoice", "Sales Invoice"),
        values_to_update="Y",
    )


def update_and_process_column(column, doctypes, values_to_update):
    delete_old_fields(column, doctypes)
    for doctype in doctypes:
        if column not in frappe.db.get_table_columns(doctype):
            continue

        frappe.db.set_value(doctype, {column: values_to_update}, "is_reverse_charge", 1)
        frappe.db.sql_ddl(
            "alter table `tab{0}` drop column {1}".format(doctype, column)
        )


def delete_old_fields(column, doctypes):
    frappe.db.delete(
        "Custom Field",
        {
            "fieldname": column,
            "dt": ("in", doctypes),
        },
    )
