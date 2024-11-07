import frappe


def before_update(doc, method=None):
    if doc.gst_hsn_code:
        frappe.flags.category_hsn_code = doc.gst_hsn_code
