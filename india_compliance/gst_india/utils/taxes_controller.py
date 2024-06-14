import json

import frappe
from frappe import _
from frappe.utils.data import flt
from erpnext.controllers.taxes_and_totals import get_round_off_applicable_accounts

from india_compliance.gst_india.overrides.transaction import (
    validate_charge_type_for_cess_non_advol_accounts,
)
from india_compliance.gst_india.utils import get_gst_accounts_by_type


@frappe.whitelist()
def set_item_wise_tax_rates(doc, item_name=None, tax_name=None):
    items, taxes = get_rows_to_update(doc, item_name, tax_name)
    tax_accounts = {tax.account_head for tax in taxes}

    if not tax_accounts:
        return

    tax_templates = {item.item_tax_template for item in items}
    item_tax_map = get_item_tax_map(tax_templates, tax_accounts)

    for tax in taxes:
        item_wise_tax_rates = (
            json.loads(tax.item_wise_tax_rates) if tax.item_wise_tax_rates else {}
        )

        for item in items:
            key = (item.item_tax_template, tax.account_head)
            item_wise_tax_rates[item.name] = item_tax_map.get(key, tax.rate)

        tax.item_wise_tax_rates = json.dumps(item_wise_tax_rates)


@frappe.whitelist()
def set_total_taxes(doc):
    total_taxes = 0

    round_off_accounts = get_round_off_applicable_accounts(doc.company, [])
    for tax in doc.taxes:
        tax.tax_amount = get_tax_amount(doc, tax.item_wise_tax_rates, tax.charge_type)

        if tax.account_head in round_off_accounts:
            tax.tax_amount = round(tax.tax_amount, 0)

        total_taxes += tax.tax_amount
        tax.base_tax_amount_after_discount_amount = total_taxes

    doc.total_taxes = total_taxes


def get_item_tax_map(tax_templates, tax_accounts):
    """
    Parameters:
        tax_templates (list): List of item tax templates used in the items
        tax_accounts (list): List of tax accounts used in the taxes

    Returns:
        dict: A map of item_tax_template, tax_account and tax_rate

    Sample Output:
        {
            ('GST 18%', 'IGST - TC'): 18.0
            ('GST 28%', 'IGST - TC'): 28.0
        }
    """

    if not tax_templates:
        return {}

    tax_rates = frappe.get_all(
        "Item Tax Template Detail",
        fields=("parent", "tax_type", "tax_rate"),
        filters={
            "parent": ("in", tax_templates),
            "tax_type": ("in", tax_accounts),
        },
    )

    return {(d.parent, d.tax_type): d.tax_rate for d in tax_rates}


def get_rows_to_update(doc, item_name=None, tax_name=None):
    """
    Returns items and taxes to update based on item_name and tax_name passed.
    If item_name and tax_name are not passed, all items and taxes are returned.
    """

    items = doc.get("items", {"name": item_name}) if item_name else doc.items
    taxes = doc.get("taxes", {"name": tax_name}) if tax_name else doc.taxes

    return items, taxes


def get_tax_amount(doc, item_wise_tax_rates, charge_type):
    if isinstance(item_wise_tax_rates, str):
        item_wise_tax_rates = json.loads(item_wise_tax_rates)

    tax_amount = 0
    for item in doc.items:
        multiplier = (
            item.qty if charge_type == "On Item Quantity" else item.taxable_value / 100
        )
        tax_amount += flt(item_wise_tax_rates.get(item.name, 0)) * multiplier

    return tax_amount


def validate_taxes(doc):
    output_accounts = get_gst_accounts_by_type(doc.company, "Output", throw=True)
    taxable_value_map = {}
    item_qty_map = {}

    for row in doc.get("items"):
        taxable_value_map[row.name] = row.taxable_value
        item_qty_map[row.name] = row.qty

    for tax in doc.taxes:
        if not tax.tax_amount:
            continue

        if tax.account_head not in output_accounts.values():
            frappe.throw(
                _("Row #{0}: Only Output accounts are allowed in {1}.").format(
                    tax.idx, doc.doctype
                )
            )

        validate_charge_type_for_cess_non_advol_accounts(
            [output_accounts.cess_non_advol_account], tax
        )


def set_taxable_value(doc):
    for item in doc.items:
        item.taxable_value = item.amount
