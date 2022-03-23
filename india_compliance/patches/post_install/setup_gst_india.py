import frappe


def execute():
    # delete_custom_field_tax_id_if_exists
    for field in frappe.db.sql_list(
        """select name from `tabCustom Field` where fieldname='tax_id'
        and dt in ('Sales Order', 'Sales Invoice', 'Delivery Note')"""
    ):
        frappe.delete_doc("Custom Field", field, ignore_permissions=True)
