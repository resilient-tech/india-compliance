import click

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from india_compliance.patches.post_install.update_e_invoice_fields_and_logs import (
    delete_custom_fields,
)

DOCTYPE = "Tax Category"
TAX_TEMPLATES = (
    "Sales Taxes and Charges Template",
    "Purchase Taxes and Charges Template",
)
CUSTOM_FIELDS_TO_CREATE = {
    TAX_TEMPLATES: [
        {
            "fieldname": "is_inter_state",
            "label": "Is Inter State",
            "fieldtype": "Check",
            "insert_after": "is_default",
            "print_hide": 1,
        }
    ],
    "Purchase Taxes and Charges Template": [
        {
            "fieldname": "is_reverse_charge",
            "label": "Is Reverse Charge",
            "fieldtype": "Check",
            "insert_after": "is_inter_state",
            "print_hide": 1,
        },
    ],
    "Supplier": [
        {
            "fieldname": "is_reverse_charge",
            "label": "Is Reverse Charge by Default",
            "fieldtype": "Check",
            "insert_after": "gst_transporter_id",
            "depends_on": "eval:doc.gst_category == 'Registered Regular'",
            "translatable": 0,
        }
    ],
}
CUSTOM_FIELDS_TO_DELETE = {
    DOCTYPE: [
        {
            "fieldname": "is_inter_state",
        },
        {
            "fieldname": "is_reverse_charge",
        },
        {
            "fieldname": "tax_category_column_break",
        },
        {
            "fieldname": "gst_state",
        },
    ],
}
DEFAULT_CATEGORIES = [
    "In-State",
    "Out-State",
    "Reverse Charge In-State",
    "Reverse Charge Out-State",
    "Registered Composition",
]


def execute():
    if not frappe.flags.in_install:
        create_custom_fields(CUSTOM_FIELDS_TO_CREATE)
        set_default_gst_settings()

    update_tax_templates()
    if not opt_out_needed():
        return switch_to_simplified_tax()

    click.secho(
        "Looks like you are using tax categories. You can opt into simplified tax for India from GST Settings.",
        color="yellow",
    )


def set_default_gst_settings():
    settings = frappe.get_doc("GST Settings")
    settings.db_set(
        {
            "reverse_charge_for_unregistered_purchase": 1,
            "reverse_charge_threshold": 5000,
        }
    )


def update_tax_templates():
    show_alert = False
    for doctype in TAX_TEMPLATES:
        doc_list = frappe.get_all(doctype, pluck="name")

        for docname in doc_list:
            doc = frappe.get_doc(doctype, docname)
            if not doc.tax_category:
                continue

            category = frappe.db.get_value(
                DOCTYPE,
                {"name": doc.tax_category},
                ["is_inter_state", "is_reverse_charge", "gst_state"],
                as_dict=True,
            )

            if category.gst_state:
                show_alert = True

            update_values = {"is_inter_state": category.is_inter_state}
            if doctype == "Purchase Taxes and Charges Template":
                update_values["is_reverse_charge"] = category.is_reverse_charge

            doc.db_set(update_values)

    if show_alert:
        frappe.msgprint(
            "State wise Tax Categories are no longer supported. If you maintain state wise GST accounts, please merge them manually."
        )


def opt_out_needed():
    categories = frappe.get_all(DOCTYPE, pluck="name")
    for category in categories:
        if category not in DEFAULT_CATEGORIES:
            return True

    for doctype in ["Customer", "Supplier", "Item Tax"]:
        if frappe.db.get_value(doctype, filters={"tax_category": ["!=", ""]}):
            return True


def switch_to_simplified_tax():
    unset_tax_categories_in_masters()
    delete_custom_fields(CUSTOM_FIELDS_TO_DELETE)

    # delete all tax categories
    frappe.db.delete(DOCTYPE)

    frappe.db.set_global("ic_switched_to_simplified_tax", 1)


def unset_tax_categories_in_masters():
    for doctype in ["Customer", "Supplier", "Item Tax", *TAX_TEMPLATES]:
        table = frappe.qb.DocType(doctype)
        frappe.qb.update(table).set("tax_category", None).where(
            (table.tax_category != "") | (table.tax_category.isnotnull())
        ).run()
