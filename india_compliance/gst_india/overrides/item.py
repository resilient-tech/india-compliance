import frappe
from frappe import _


def validate_hsn_code(doc, method=None):
    gst_settings = frappe.get_single("GST Settings")
    if not doc.is_sales_item or not gst_settings.hsn_validation:
        return

    if not doc.gst_hsn_code:
        frappe.throw(_("HSN/SAC Code is mandatory. Please enter a valid HSN/SAC code.").format(doc.item_name))
    elif len(doc.gst_hsn_code) < int(gst_settings.hsn_digits):
        frappe.throw(_("HSN/SAC Code should be atleast {0} digits. Please enter a valid HSN/SAC code.").format(gst_settings.hsn_digits))