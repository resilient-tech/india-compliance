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
                not row.base_tax_amount_after_discount_amount
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


class TaxesController:
    @frappe.whitelist()
    def set_item_wise_tax_rates(self, item_name=None, tax_name=None):
        items, taxes = self.get_rows_to_update(item_name, tax_name)

        tax_accounts = {tax.account_head for tax in taxes}

        if not tax_accounts:
            return

        tax_templates = {item.item_tax_template for item in items}
        item_tax_map = self.get_item_tax_map(tax_templates, tax_accounts)

        for tax in taxes:
            item_wise_tax_rates = (
                json.loads(tax.item_wise_tax_rates) if tax.item_wise_tax_rates else {}
            )

            for item in items:
                key = f"{item.item_tax_template},{tax.account_head}"
                item_wise_tax_rates[item.name] = item_tax_map.get(key, tax.rate)

            tax.item_wise_tax_rates = json.dumps(item_wise_tax_rates)

    def get_item_tax_map(self, tax_templates, tax_accounts):
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
        items = self.get("items", {"name": item_name}) if item_name else self.items
        taxes = (
            self.get(self.FIELD_MAP.get("taxes"), {"name": tax_name})
            if tax_name
            else self.taxes
        )

        return items, taxes

    def get_tax_amount(self, item_wise_tax_rates, charge_type):
        if isinstance(item_wise_tax_rates, str):
            item_wise_tax_rates = json.loads(item_wise_tax_rates)

        tax_amount = 0
        for item in self.items:
            multiplier = (
                item.get(self.FIELD_MAP.get("qty"))
                if charge_type == "On Item Quantity"
                else item.taxable_value / 100
            )
            tax_amount += flt(item_wise_tax_rates.get(item.name, 0)) * multiplier

        return tax_amount


class SubcontractingTaxesController(TaxesController):
    def set_base_tax_amount_and_tax_total(self):
        total_taxes = 0

        round_off_accounts = get_round_off_applicable_accounts(self.company, [])
        for tax in self.get(self.FIELD_MAP.get("taxes")):
            tax_amount = self.get_tax_amount(tax.item_wise_tax_rates, tax.charge_type)

            if tax.account_head in round_off_accounts:
                tax_amount = round(tax_amount, 0)

            total_taxes += tax_amount

            setattr(tax, self.FIELD_MAP.get("tax_amount"), tax_amount)
            tax.base_total = (
                self.get(self.FIELD_MAP.get("total_taxable_value")) + total_taxes
            )

        setattr(self, self.FIELD_MAP.get("total_taxes"), total_taxes)

    def set_base_rounded_total(self):
        total = self.get(self.FIELD_MAP.get("total_taxable_value")) + self.get(
            self.FIELD_MAP.get("total_taxes")
        )

        setattr(self, self.FIELD_MAP.get("grand_total"), total)

    def set_total_taxable_value(self):
        if self.doctype != "Stock Entry":
            return
        total = 0
        for item in self.items:
            total += item.taxable_value

        self.total_taxable_value = total

    def validate_taxes(self):
        gst_accounts = get_all_gst_accounts(self.get(self.FIELD_MAP.get("company")))
        for tax in self.get(self.FIELD_MAP.get("taxes")):
            if not tax.base_tax_amount_after_discount_amount:
                continue

            if tax.account_head not in gst_accounts:
                frappe.throw(
                    _("Row #{0}: Only GST accounts are allowed in {1}.").format(
                        tax.idx, self.doctype
                    )
                )

    def set_taxable_value(self):
        for item in self.items:
            item.taxable_value = item.get(self.FIELD_MAP.get("amount"))

    def validate_taxes_and_transaction(self):
        self.validate_taxes()
        validate_transaction(self)

    def set_taxes_and_totals(self):
        self.set_item_wise_tax_rates()
        self.set_taxable_value()
        self.set_total_taxable_value()
        self.set_base_tax_amount_and_tax_total()
        self.set_base_rounded_total()
