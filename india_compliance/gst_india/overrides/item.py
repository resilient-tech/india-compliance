import frappe

from india_compliance.gst_india.doctype.gst_hsn_code.gst_hsn_code import (
    validate_hsn_code as _validate_hsn_code,
)


def validate(doc, method=None):
    validate_hsn_code(doc)
    set_taxes_from_hsn_code(doc)


def validate_hsn_code(doc):
    # HSN Code is being validated only for sales items
    if not doc.is_sales_item:
        return

    _validate_hsn_code(doc.gst_hsn_code)


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
