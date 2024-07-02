import json

import frappe
from frappe import _
from frappe.utils.data import flt
from erpnext.controllers.taxes_and_totals import get_round_off_applicable_accounts

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.overrides.transaction import (
    ItemGSTDetails,
    ItemGSTTreatment,
    validate_transaction,
)
from india_compliance.gst_india.utils import get_all_gst_accounts


class CustomItemGSTDetails(ItemGSTDetails):
    """
    Support use of Item wise tax rates in Taxes and Charges table
    """

    FIELDMAP = {"taxes": "taxes", "qty": "qty"}

    def set_item_wise_tax_details(self):
        tax_details = frappe._dict()
        item_map = {}

        for row in self.doc.get("items"):
            key = row.name
            item_map[key] = row
            tax_details[key] = self.item_defaults.copy()
            tax_details[key]["count"] += 1

        for row in self.doc.get(self.FIELDMAP.get("taxes")):
            if (
                not row.tax_amount
                or row.gst_tax_type not in GST_TAX_TYPES
                or not row.item_wise_tax_rates
            ):
                continue

            tax = row.gst_tax_type
            tax_rate_field = f"{tax}_rate"
            tax_amount_field = f"{tax}_amount"

            item_wise_tax_rates = json.loads(row.item_wise_tax_rates)

            # update item taxes
            for row_name in item_wise_tax_rates:
                if row_name not in tax_details:
                    # Do not compute if Item is not present in Item table
                    # There can be difference in Item Table and Item Wise Tax Details
                    continue

                item_taxes = tax_details[row_name]
                tax_rate = item_wise_tax_rates.get(row_name)
                precision = self.precision.get(tax_amount_field)
                item = item_map.get(row_name)

                multiplier = (
                    item.get(self.FIELDMAP.get("qty"))
                    if tax == "cess_non_advol"
                    else item.taxable_value / 100
                )

                # cases when charge type == "Actual"
                if not tax_rate:
                    continue

                tax_amount = flt(tax_rate * multiplier, precision)
                item_taxes[tax_rate_field] = tax_rate
                item_taxes[tax_amount_field] += tax_amount

        self.item_tax_details = tax_details

    def get_item_key(self, item):
        return item.name


def update_gst_details(doc, method=None):
    # TODO: add item tax template validation post exclude from GST
    ItemGSTTreatment().set(doc)
    CustomItemGSTDetails().update(doc)


@frappe.whitelist()
def set_item_wise_tax_rates(
    doc, field_map, item_name=None, tax_name=None, is_client=False
):
    if is_client:
        doc = frappe._dict(frappe.parse_json(doc))
    items, taxes = get_rows_to_update(doc, field_map, item_name, tax_name)
    tax_accounts = {tax.get("account_head") for tax in taxes}
    if not tax_accounts:
        return

    tax_templates = {item.get("item_tax_template") for item in items}
    item_tax_map = get_item_tax_map(tax_templates, tax_accounts)

    for tax in taxes:
        item_wise_tax_rates = (
            json.loads(tax.get("item_wise_tax_rates"))
            if tax.get("item_wise_tax_rates")
            else {}
        )

        for item in items:
            key = f'{item.get("item_tax_template")},{tax.get("account_head")}'
            item_wise_tax_rates[item.get("name")] = item_tax_map.get(
                key, tax.get("rate")
            )

        if is_client:
            tax["item_wise_tax_rates"] = json.dumps(item_wise_tax_rates)
        else:
            tax.item_wise_tax_rates = json.dumps(item_wise_tax_rates)

    if is_client:
        return taxes


def set_base_tax_amount_and_tax_total(doc, field_map):
    total_taxes = 0
    round_off_accounts = get_round_off_applicable_accounts(doc.company, [])

    for tax in doc.get(field_map.get("taxes")):
        tax.tax_amount = get_tax_amount(
            doc, tax.item_wise_tax_rates, tax.charge_type, field_map
        )
        if tax.account_head in round_off_accounts:
            tax.tax_amount = round(tax.tax_amount, 0)

        total_taxes += tax.tax_amount

        tax.base_total = total_taxes + doc.get(field_map.get("total_taxable_value"))

    setattr(doc, field_map.get("total_taxes"), total_taxes)


def set_base_rounded_total(doc, field_map):
    total = 0
    for item in doc.items:
        total += item.taxable_value

    total += doc.get(field_map.get("total_taxes"))

    setattr(doc, field_map.get("grand_total"), total)


@frappe.whitelist()
def get_item_tax_map(tax_templates, tax_accounts):
    """
    Parameters:
        tax_templates (list): List of item tax templates used in the items
        tax_accounts (list): List of tax accounts used in the taxes

    Returns:
        dict: A map of item_tax_template, tax_account and tax_rate

    Sample Output:
        {
            'GST 18%,IGST - TC': 18.0
            'GST 28%,IGST - TC': 28.0
        }
    """
    tax_templates = frappe.parse_json(tax_templates)
    tax_accounts = frappe.parse_json(tax_accounts)

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

    return {f"{tax.parent},{tax.tax_type}": tax.tax_rate for tax in tax_rates}


def get_rows_to_update(doc, field_map, item_name=None, tax_name=None):
    """
    Returns items and taxes to update based on item_name and tax_name passed.
    If item_name and tax_name are not passed, all items and taxes are returned.
    """
    items = doc.get("items", {"name": item_name}) if item_name else doc.items
    taxes = (
        doc.get(field_map.get("taxes"), {"name": tax_name}) if tax_name else doc.taxes
    )

    return items, taxes


def get_tax_amount(doc, item_wise_tax_rates, charge_type, field_map):
    if isinstance(item_wise_tax_rates, str):
        item_wise_tax_rates = json.loads(item_wise_tax_rates)

    tax_amount = 0
    for item in doc.items:
        multiplier = (
            item.get(field_map.get("qty"))
            if charge_type == "On Item Quantity"
            else item.taxable_value / 100
        )
        tax_amount += flt(item_wise_tax_rates.get(item.name, 0)) * multiplier

    return tax_amount


def validate_taxes(doc, field_map):
    gst_accounts = get_all_gst_accounts(doc.get(field_map.get("company")))
    for tax in doc.get(field_map.get("taxes")):
        if not tax.tax_amount:
            continue

        if tax.account_head not in gst_accounts:
            frappe.throw(
                _("Row #{0}: Only GST accounts are allowed in {1}.").format(
                    tax.idx, doc.doctype
                )
            )


def set_taxable_value(doc, field_map):
    for item in doc.items:
        item.taxable_value = item.get(field_map.get("amount"))


def validate_taxes_and_transaction(doc, field_map):
    validate_taxes(doc, field_map)
    validate_transaction(doc)


def set_taxes_and_totals(doc, field_map):
    set_item_wise_tax_rates(doc, field_map)
    set_taxable_value(doc, field_map)
    set_base_tax_amount_and_tax_total(doc, field_map)
    set_base_rounded_total(doc, field_map)
