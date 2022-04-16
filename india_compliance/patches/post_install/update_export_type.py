import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from india_compliance.gst_india.constants.custom_fields import EXPORT_TYPE_FIELD

DOCTYPES = ("Sales Invoice", "Purchase Invoice")


def execute():
    column = "export_type"

    delete_old_field(column)
    for doctype in DOCTYPES:
        if column not in frappe.db.get_table_columns(doctype):
            continue

        if is_export_type_field_available(doctype):
            frappe.db.set_value(
                doctype,
                {column: "With Payment of Tax"},
                "export_with_payment_of_tax",
                1,
            )

        frappe.db.sql_ddl(
            "alter table `tab{doctype}` drop column {column_name}".format(
                doctype=doctype, column_name=column
            )
        )
        frappe.reload_doc("accounts", "doctype", frappe.scrub(doctype), force=True)


def is_export_type_field_available(doctype):
    return enable_overseas_transaction_in_gst_settings(doctype)


def enable_overseas_transaction_in_gst_settings(doctype):
    if not is_export_type_applicable(doctype):
        return

    create_custom_fields(EXPORT_TYPE_FIELD)
    return frappe.db.set_value("GST Settings", None, "enable_overseas_transactions", 1)


def is_export_type_applicable(doctype):
    condition = " where export_type = 'With Payment of Tax'"
    condition += " and gst_category in ('SEZ', 'Overseas')"

    return frappe.db.sql(
        """
			select name from `tab{doctype}` {condition} limit 1
		""".format(
            doctype=doctype, condition=condition
        )
    )


def delete_old_field(column):
    frappe.db.delete("Custom Field", {"fieldname": column, "dt": ("in", DOCTYPES)})
