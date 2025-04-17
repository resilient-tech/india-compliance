import json

import frappe
from frappe import _
from frappe.utils.data import flt
from erpnext.controllers.taxes_and_totals import (
    get_round_off_applicable_accounts as fetch_round_off_accounts,
)

from india_compliance.gst_india.overrides.transaction import (
    ItemGSTDetails,
    ItemGSTTreatment,
)
from india_compliance.gst_india.utils import get_all_gst_accounts


class CustomItemGSTDetails(ItemGSTDetails):
    """
    Support use of Item wise tax rates in Taxes and Charges table
    """

    def get_item_key(self, item):
        return item.name

    @staticmethod
    def tax_amount_field():
        return "tax_amount"

    @staticmethod
    def tax_details_field():
        return "item_wise_tax_rates"

    def get_item_tax_rate(self, item, tax_row):
        """
        Get item tax rate from item tax template
        """
        item_tax_rates = self.get_tax_details(tax_row)
        return item_tax_rates.get(item.name)


def update_gst_details(doc, method=None):
    # TODO: add item tax template validation post exclude from GST
    ItemGSTTreatment().set(doc)
    CustomItemGSTDetails().update(doc)


@frappe.whitelist()
def set_item_wise_tax_rates(doc, item_name=None, tax_name=None):
    doc = json.loads(doc, object_hook=frappe._dict)
    CustomTaxController(doc).set_item_wise_tax_rates(item_name, tax_name)

    frappe.response.docs.append(doc)


class CustomTaxController:

    def __init__(self, doc, field_map=None):
        """
        example_field_map = {
            "amount": "amount",
            "base_grand_total": "base_grand_total",
            "total_taxes": "total_taxes",
        }
        """

        self.doc = doc
        self.field_map = field_map or {}

    def set_taxes_and_totals(self):
        self.set_item_wise_tax_rates()
        self.update_item_taxable_value()
        self.update_tax_amount()
        self.update_base_grand_total()

    def set_item_wise_tax_rates(self, item_name=None, tax_name=None):
        """
        Update item wise tax rates in taxes table
        """
        items, taxes = self.get_rows_to_update(item_name, tax_name)
        tax_accounts = {tax.account_head for tax in taxes}
        if not tax_accounts:
            return

        tax_templates = {item.item_tax_template for item in items}
        item_tax_map = self.get_item_tax_map(tax_templates, tax_accounts)

        for tax in taxes:
            if tax.charge_type == "Actual":
                if not tax.item_wise_tax_rates:
                    tax.item_wise_tax_rates = "{}"

                continue

            item_wise_tax_rates = (
                json.loads(tax.item_wise_tax_rates) if tax.item_wise_tax_rates else {}
            )

            for item in items:
                key = f"{item.item_tax_template},{tax.account_head}"
                item_wise_tax_rates[item.name] = item_tax_map.get(key, tax.rate)

            tax.item_wise_tax_rates = json.dumps(item_wise_tax_rates)

        return taxes

    def update_item_taxable_value(self):
        for item in self.doc.get("items"):
            item.taxable_value = self.get_value("amount", item)

    def update_tax_amount(self):
        total_taxes = 0
        total_taxable_value = self.calculate_total_taxable_value()
        round_off_accounts = fetch_round_off_accounts(self.doc.company, [])

        for tax in self.doc.taxes:
            if tax.charge_type == "Actual":
                continue

            tax.tax_amount = self.get_tax_amount(
                tax.item_wise_tax_rates, tax.charge_type
            )

            if tax.account_head in round_off_accounts:
                tax.tax_amount = round(tax.tax_amount, 0)

            total_taxes += tax.tax_amount
            tax.base_total = total_taxes + total_taxable_value

        setattr(self.doc, self.get_fieldname("total_taxes"), total_taxes)

    def update_base_grand_total(self):
        total = self.calculate_total_taxable_value() + self.get_value("total_taxes")
        setattr(self.doc, self.get_fieldname("base_grand_total"), total)

    @staticmethod
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

    def get_rows_to_update(self, item_name=None, tax_name=None):
        """
        Returns items and taxes to update based on item_name and tax_name passed.
        If item_name and tax_name are not passed, all items and taxes are returned.
        """
        items = (
            self.doc.get("items", {"name": item_name})
            if item_name
            else self.doc.get("items")
        )
        taxes = (
            self.doc.get("taxes", {"name": tax_name}) if tax_name else self.doc.taxes
        )

        return items, taxes

    def get_tax_amount(self, item_wise_tax_rates, charge_type):
        if isinstance(item_wise_tax_rates, str):
            item_wise_tax_rates = json.loads(item_wise_tax_rates)

        tax_amount = 0
        for item in self.doc.get("items"):
            multiplier = (
                item.qty
                if charge_type == "On Item Quantity"
                else item.taxable_value / 100
            )
            tax_amount += flt(item_wise_tax_rates.get(item.name, 0)) * multiplier

        return tax_amount

    def calculate_total_taxable_value(self):
        return sum([item.taxable_value for item in self.doc.get("items")])

    def get_value(self, field, doc=None, default=0):
        doc = doc or self.doc

        if field in self.field_map:
            return doc.get(self.field_map.get(field), default)

        return doc.get(field, default)

    def get_fieldname(self, field):
        return self.field_map.get(field, field)


def validate_taxes(doc):
    gst_accounts = get_all_gst_accounts(doc.company)
    for tax in doc.taxes:
        if not tax.tax_amount:
            continue

        if tax.account_head not in gst_accounts:
            frappe.throw(
                _("Row #{0}: Only GST accounts are allowed in {1}.").format(
                    tax.idx, doc.doctype
                )
            )
