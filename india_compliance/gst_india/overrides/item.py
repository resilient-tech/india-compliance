import frappe
from frappe import _


def validate(doc, method=None):
    validate_hsn_code(doc)
    set_taxes_from_hsn_code(doc)


def validate_hsn_code(doc):
    # HSN Code is being validated only for sales items
    if not doc.is_sales_item:
        return

    validate_hsn_code, min_hsn_digits = frappe.get_cached_value(
        "GST Settings",
        "GST Settings",
        ("validate_hsn_code", "min_hsn_digits"),
    )

    if not validate_hsn_code:
        return

    if not doc.gst_hsn_code:
        frappe.throw(
            _("HSN/SAC Code is required. Please enter a valid HSN/SAC code.").format(
                doc.item_name
            ),
            frappe.MandatoryError,
        )

    if len(doc.gst_hsn_code) < int(min_hsn_digits):
        frappe.throw(
            _(
                "HSN/SAC Code should be at least {0} digits long. Please enter a valid"
                " HSN/SAC code."
            ).format(min_hsn_digits)
        )


def set_taxes_from_hsn_code(doc):
    if doc.taxes or not doc.gst_hsn_code:
        return

    hsn_doc = frappe.get_doc("GST HSN Code", doc.gst_hsn_code)

    for tax in hsn_doc.taxes:
        doc.append(
            "taxes",
            {
                "item_tax_template": tax.item_tax_template,
                "tax_category": tax.tax_category,
                "valid_from": tax.valid_from,
            },
        )
