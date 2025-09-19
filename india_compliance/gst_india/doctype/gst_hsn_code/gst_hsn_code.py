# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document, bulk_insert
from frappe.utils import random_string

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
    """Update taxes for all items with the given HSN code using bulk operations for performance."""
    taxes = frappe.parse_json(taxes)
    items = frappe.get_list("Item", filters={"gst_hsn_code": hsn_code}, pluck="name")

    if not items:
        return

    frappe.db.delete("Item Tax", {"parent": ["in", items]})

    if taxes:
        _bulk_insert_item_taxes(items, taxes)

    _update_item_modified_timestamp(items)


def _bulk_insert_item_taxes(item_names, taxes):
    documents = []
    for item_name in item_names:
        for index, tax in enumerate(taxes):
            tax = frappe._dict(tax)
            doc = frappe.new_doc("Item Tax")
            doc.update(
                {
                    "name": random_string(10),
                    "parent": item_name,
                    "parenttype": "Item",
                    "parentfield": "taxes",
                    "item_tax_template": tax.get("item_tax_template"),
                    "tax_category": tax.get("tax_category"),
                    "valid_from": tax.get("valid_from"),
                    "minimum_net_rate": tax.get("minimum_net_rate", 0),
                    "maximum_net_rate": tax.get("maximum_net_rate", 0),
                    "idx": tax.get("idx", index + 1),
                }
            )
            documents.append(doc)

    if documents:
        bulk_insert("Item Tax", documents)


def _update_item_modified_timestamp(item_names):
    item = frappe.qb.DocType("Item")
    (
        frappe.qb.update(item)
        .set(item.modified, frappe.utils.now())
        .set(item.modified_by, frappe.session.user)
        .where(frappe.qb.DocType("Item").name.isin(item_names))
    ).run()


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
