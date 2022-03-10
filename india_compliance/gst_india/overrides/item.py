import frappe
from frappe import _


def validate_hsn_code(doc, method=None):
    # HSN Code is being validated only for sales items
    if not doc.is_sales_item:
        return

    gst_settings = frappe.db.get_value(
        "GST Settings",
        "GST Settings",
        ("validate_hsn_code", "min_hsn_digits"),
        as_dict=True,
    )

    if not gst_settings or not gst_settings.validate_hsn_code:
        return

    if not doc.gst_hsn_code:
        frappe.throw(
            _("HSN/SAC Code is required. Please enter a valid HSN/SAC code.").format(
                doc.item_name
            ),
            frappe.MandatoryError,
        )

    if len(doc.gst_hsn_code) < int(gst_settings.min_hsn_digits):
        frappe.throw(
            _(
                "HSN/SAC Code should be atleast {0} digits long. Please enter a valid"
                " HSN/SAC code."
            ).format(gst_settings.min_hsn_digits)
        )
