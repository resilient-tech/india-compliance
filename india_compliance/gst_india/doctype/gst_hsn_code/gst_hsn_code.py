# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
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
    taxes = frappe.parse_json(taxes)
    items = frappe.get_list("Item", filters={"gst_hsn_code": hsn_code}, pluck="name")

    if not items:
        return

    frappe.db.delete("Item Tax", {"parent": ["in", items]})

    timestamp = frappe.utils.now()

    if taxes:
        _bulk_insert_item_taxes(items, taxes, timestamp)

    _update_item_modified_timestamp(items, timestamp)
    _add_comment_to_items(items, hsn_code, timestamp)


def _bulk_insert_item_taxes(item_names, taxes, timestamp=None):
    timestamp = timestamp or frappe.utils.now()

    values = []
    fields = (
        "name",
        "parent",
        "parenttype",
        "parentfield",
        "item_tax_template",
        "tax_category",
        "valid_from",
        "minimum_net_rate",
        "maximum_net_rate",
        "idx",
        "creation",
        "modified",
        "modified_by",
        "owner",
    )

    for item_name in item_names:
        for index, tax in enumerate(taxes):
            tax = frappe._dict(tax)
            values.append(
                (
                    random_string(10),  # name
                    item_name,  # parent
                    "Item",  # parenttype
                    "taxes",  # parentfield
                    tax.get("item_tax_template"),
                    tax.get("tax_category"),
                    tax.get("valid_from"),
                    tax.get("minimum_net_rate", 0),
                    tax.get("maximum_net_rate", 0),
                    tax.get("idx", index + 1),
                    timestamp,  # creation
                    timestamp,  # modified
                    frappe.session.user,  # modified_by
                    frappe.session.user,  # owner
                )
            )

    if values:
        frappe.db.bulk_insert("Item Tax", fields, values)


def _update_item_modified_timestamp(item_names, timestamp=None):
    item = frappe.qb.DocType("Item")
    (
        frappe.qb.update(item)
        .set(item.modified, timestamp or frappe.utils.now())
        .set(item.modified_by, frappe.session.user)
        .where(item.name.isin(item_names))
    ).run()


def _add_comment_to_items(item_names, hsn_code, timestamp=None):
    if not item_names:
        return

    fields = (
        "name",
        "comment_type",
        "comment_email",
        "comment_by",
        "creation",
        "modified",
        "modified_by",
        "owner",
        "reference_doctype",
        "reference_name",
        "content",
    )

    comment_text = f"changed item tax from GST HSN Code {hsn_code}"

    comment_docs = []
    current_time = timestamp or frappe.utils.now()
    current_user = frappe.session.user

    for item_name in item_names:
        comment_docs.append(
            (
                random_string(10),  # name
                "Info",  # comment_type
                current_user,  # comment_email
                current_user,  # comment_by
                current_time,  # creation
                current_time,  # modified
                current_user,  # modified_by
                current_user,  # owner
                "Item",  # reference_doctype
                item_name,  # reference_name
                comment_text,  # content
            )
        )

    if comment_docs:
        frappe.db.bulk_insert("Comment", fields, comment_docs)


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
