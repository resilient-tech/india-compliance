import frappe

from india_compliance.gst_india.constants.custom_fields import (
    SALES_REVERSE_CHARGE_FIELDS,
)
from india_compliance.gst_india.utils import toggle_custom_fields

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
    set_default_gst_settings()


def delete_old_fields():
    frappe.db.delete(
        "Custom Field",
        {
            "fieldname": "reverse_charge",
            "dt": ("in", DOCTYPES),
        },
    )


def set_default_gst_settings():
    invoice = frappe.get_value(
        "Sales Invoice",
        {"is_reverse_charge": 1, "posting_date": [">", "2019-04-01"]},
        "name",
    )
    if not invoice:
        return toggle_custom_fields(SALES_REVERSE_CHARGE_FIELDS, False)

    frappe.set_value("GST Settings", None, "enable_reverse_charge_in_sales", 1)
    toggle_custom_fields(SALES_REVERSE_CHARGE_FIELDS, True)
