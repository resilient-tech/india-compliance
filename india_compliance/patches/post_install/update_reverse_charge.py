import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    update_reverse_charge_in_sales_transaction()
    enable_reverse_charge_in_gst_settings()


def update_reverse_charge_in_sales_transaction():
    column = "reverse_charge"
    to_remove = ["Sales Invoice", "Purchase Invoice"]
    field_to_create = "is_reverse_charge"

    for doctype in to_remove:
        if frappe.db.table_exists(doctype):
            if column in frappe.db.get_table_columns(doctype):
                invoices_to_update = frappe.db.get_all(doctype, {column: "Y"}, ["name"])

                frappe.db.sql(
                    "alter table `tab{0}` drop column {1}".format(doctype, column)
                )

                create_custom_fields(doctype, field_to_create)
                update_reverse_charge_in_invoices(
                    doctype, invoices_to_update, field_to_create
                )

    frappe.reload_doc("accounts", "doctype", "sales_invoice", force=True)
    frappe.reload_doc("buying", "doctype", "purchase_invoice", force=True)


def create_custom_field(doctype, field_to_create):
    REVERSE_CHARGE_FIELD = {
        doctype: [
            {
                "fieldname": field_to_create,
                "label": "Is Reverse Charge",
                "fieldtype": "Check",
                "insert_after": "is_debit_note"
                if doctype == "Sales Invoice"
                else "apply_tds",
                "print_hide": 1,
                "default": 0,
            },
        ]
    }

    create_custom_fields(REVERSE_CHARGE_FIELD, update=True)


def update_reverse_charge_in_invoices(doctype, invoices_to_update, field_to_create):
    frappe.db.set_value(
        doctype,
        {
            "name": [
                "in",
                [invoice["name"] for invoice in invoices_to_update],
            ]
        },
        field_to_create,
        1,
    )


def enable_reverse_charge_in_gst_settings():
    doctype = "Sales Invoice"
    if reverse_charge_applied(doctype):
        frappe.db.set_value("GST Settings", None, "enable_reverse_charge", 1)
    else:
        frappe.db.set_value("GST Settings", None, "enable_reverse_charge", 0)
        frappe.db.delete(
            "Custom Field", {"dt": doctype, "fieldname": "is_reverse_charge"}
        )


def reverse_charge_applied(doctype):
    condition = " where is_reverse_charge = 1"

    return frappe.db.sql(
        "select name from `tab{doctype}` {condition} limit 1".format(
            doctype=doctype, condition=condition
        )
    )
