import frappe


def execute():
    frappe.delete_doc_if_exists("Print Format", "GST E-Invoice")
