import frappe


def execute():
    frappe.db.set_default("add_taxes_from_item_tax_template", 0)
