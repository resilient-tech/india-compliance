import frappe


def execute():
    bill_of_entry_item = frappe.qb.DocType("Bill of Entry Item")
    frappe.qb.update(bill_of_entry_item).set("gst_treatment", "Zero-Rated")
