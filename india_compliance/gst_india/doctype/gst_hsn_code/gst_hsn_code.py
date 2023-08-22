# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document, bulk_insert

from india_compliance.gst_india.utils import (
    get_hsn_settings,
    join_list_with_custom_separators,
)


class GSTHSNCode(Document):
    def validate(self):
        validate_hsn_code(self.hsn_code)


@frappe.whitelist()
def update_taxes_in_item_master(taxes, hsn_code):
    frappe.enqueue(update_item_document, taxes=taxes, hsn_code=hsn_code, queue="long")
    return 1


def update_item_document(taxes, hsn_code):
    taxes = frappe.parse_json(taxes)
    items = frappe.get_list("Item", filters={"gst_hsn_code": hsn_code})

    while items:
        items_to_update = items[:10_000]

        frappe.db.delete(
            "Item Tax", {"parenttype": "Item", "parent": ("in", items_to_update)}
        )
        bulk_insert("Item Tax", _get_taxes_to_insert(items_to_update, taxes))
        frappe.db.commit()

        items = items[10_000:]


def _get_taxes_to_insert(items, taxes):
    for item in items:
        for index, tax in enumerate(taxes, 1):
            yield frappe.get_doc(
                {
                    "doctype": "Item Tax",
                    "parenttype": "Item",
                    "parent": item.name,
                    "item_tax_template": tax.item_tax_template,
                    "tax_category": tax.tax_category,
                    "valid_from": tax.valid_from,
                    "idx": index,
                }
            )


def validate_hsn_code(hsn_code):
    validate_hsn_code, valid_hsn_length = get_hsn_settings()

    if not validate_hsn_code:
        return

    if not hsn_code:
        frappe.throw(
            _("HSN/SAC Code is required. Please enter a valid HSN/SAC code."),
            frappe.MandatoryError,
        )

    if len(hsn_code) not in valid_hsn_length:
        frappe.throw(
            _(
                "HSN/SAC Code should be {0} digits long. Please enter a valid"
                " HSN/SAC code."
            ).format(join_list_with_custom_separators(valid_hsn_length)),
            title=_("Invalid HSN/SAC"),
        )
