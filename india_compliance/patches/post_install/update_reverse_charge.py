import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    column = "reverse_charge"

    for doctype in ("Purchase Invoice", "Sales Invoice"):
        if frappe.db.table_exists(doctype):
            if column in frappe.db.get_table_columns(doctype):
                if enable_reverse_charge_in_gst_settings(doctype):
                    create_custom_fields(doctype, "is_reverse_charge")

                frappe.db.set_value(
                    doctype, {"reverse_charge": "Y"}, "is_reverse_charge", 1
                )
                frappe.db.sql(
                    "alter table `tab{0}` drop column 'reverse_charge'".format(doctype)
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


def enable_reverse_charge_in_gst_settings(doctype):
    if doctype == "Sales Invoice" and not reverse_charge_applicable(doctype):
        return

    if doctype == "Purchase Invoice":
        return

    return frappe.db.set_value("GST Settings", None, "enable_reverse_charge", 1)


def reverse_charge_applicable(doctype):
    condition = " where reverse_charge = 'Y'"

    return frappe.db.sql(
        "select name from `tab{doctype}` {condition} limit 1".format(
            doctype=doctype, condition=condition
        )
    )
