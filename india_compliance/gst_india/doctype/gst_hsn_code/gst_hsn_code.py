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
from india_compliance.utils.change_log_utils import add_comments_in_bulk


class GSTHSNCode(Document):
    def validate(self):
        validate_hsn_code(self.hsn_code)


@frappe.whitelist()
def update_taxes_in_item_master(taxes: str | list, hsn_code: str):
    frappe.has_permission("Item", "write", throw=True)

    frappe.enqueue(update_item_document, taxes=taxes, hsn_code=hsn_code, queue="long")
    return 1


def update_item_document(taxes, hsn_code):
    taxes = frappe.parse_json(taxes)
    items = frappe.get_list("Item", filters={"gst_hsn_code": hsn_code}, pluck="name")

    if not items:
        return

    frappe.db.delete("Item Tax", {"parent": ["in", items]})

    if taxes:
        _bulk_insert_item_taxes(items, taxes)

    timestamp = frappe.utils.now()

    _update_item_modified_timestamp(items, timestamp)
    _add_comment_to_items(items, hsn_code, timestamp)


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


def _update_item_modified_timestamp(item_names, timestamp=None):
    item = frappe.qb.DocType("Item")
    (
        frappe.qb.update(item)
        .set(item.modified, timestamp or frappe.utils.now())
        .set(item.modified_by, frappe.session.user)
        .where(item.name.isin(item_names))
    ).run()


def _add_comment_to_items(item_names, hsn_code, timestamp=None):
    comment_text = f"changed item tax from GST HSN Code {hsn_code}"

    add_comments_in_bulk(
        (("Item", item_name, comment_text) for item_name in item_names),
        timestamp=timestamp,
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
            _("HSN/SAC Code should be {0} digits long. Please enter a valid HSN/SAC code.").format(
                join_list_with_custom_separators(valid_hsn_length)
            ),
            title=_("Invalid HSN/SAC"),
        )
