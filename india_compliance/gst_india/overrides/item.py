import frappe
from frappe import _

from india_compliance.gst_india.utils import (
    get_hsn_settings,
    join_list_with_custom_separators,
)


def validate(doc, method=None):
    validate_hsn_code(doc)
    set_taxes_from_hsn_code(doc)


def validate_hsn_code(doc):
    # HSN Code is being validated only for sales items
    if not doc.is_sales_item:
        return

    validate_hsn_code, valid_hsn_length = get_hsn_settings()

    if not validate_hsn_code:
        return

    if not doc.gst_hsn_code:
        frappe.throw(
            _("HSN/SAC Code is required. Please enter a valid HSN/SAC code.").format(
                doc.item_name
            ),
            frappe.MandatoryError,
        )

    if len(doc.gst_hsn_code) not in valid_hsn_length:
        frappe.throw(
            _(
                "HSN/SAC Code should be {0} digits long. Please enter a valid"
                " HSN/SAC code."
            ).format(join_list_with_custom_separators(valid_hsn_length)),
            title=_("Invalid HSN/SAC"),
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
