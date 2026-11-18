import frappe


def before_update(doc, method=None):
    # the custom field is added after the other app's own install has created records
    if hsn_code := doc.get("gst_hsn_code"):
        frappe.flags.cross_app_hsn_code = hsn_code
