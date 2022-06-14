import frappe

DOCTYPES = ("Purchase Invoice", "Sales Invoice")


def execute():
    column = "reverse_charge"

    delete_old_fields()
    for doctype in DOCTYPES:
        if column not in frappe.db.get_table_columns(doctype):
            continue

        frappe.db.set_value(doctype, {column: "Y"}, "is_reverse_charge", 1)
        frappe.db.sql_ddl(
            "alter table `tab{0}` drop column {1}".format(doctype, column)
        )


def delete_old_fields():
    frappe.db.delete(
        "Custom Field",
        {
            "fieldname": "reverse_charge",
            "dt": ("in", DOCTYPES),
        },
    )
