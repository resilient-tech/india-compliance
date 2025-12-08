import json
from collections import defaultdict

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

    def set_temp_item_wise_tax_detail_object(self):
        self.doc._item_wise_tax_details = []
        item_map = {item.name: item for item in self.doc.items}

        for row in self.doc.taxes:
            if not row.gst_tax_type:
                continue

            item_wise_tax_rates = self.get_tax_details(row)
            for item_name, rate in item_wise_tax_rates.items():
                item = item_map.get(item_name)
                if not item:
                    continue

                self.doc._item_wise_tax_details.append(
                    frappe._dict(
                        {
                            "item": item,
                            "tax": row,
                            "rate": rate,
                        }
                    )
                )

    def build_item_wise_tax_detail_from_data(self):
        """
        Build item_wise_tax_details structure from JSON for patch/get operations.
        This mimics the child table structure expected by base class get_item_name_wise_tax_details()
        """
        self.doc.item_wise_tax_details = []

        for row in self.doc.taxes:
            if not row.gst_tax_type:
                continue

            item_wise_tax_rates = self.get_tax_details(row)
            for item_name, rate in item_wise_tax_rates.items():
                self.doc.item_wise_tax_details.append(
                    frappe._dict(
                        {
                            "item_row": item_name,
                            "tax_row": row.name,
                            "rate": rate,
                        }
                    )
                )


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
        self.set_additional_taxable_value()
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
            taxable_value = self.get_value("amount", item)
            taxable_value += flt(
                item.get("additional_taxable_value", 0), item.precision("taxable_value")
            )

            item.taxable_value = taxable_value

    def set_additional_taxable_value(self):
        if self.doc.doctype != "Stock Entry" or not self.doc.items:
            return

        for item in self.doc.items:
            item.additional_taxable_value = 0

        if self.doc.purpose == "Subcontracting Delivery":
            _set_subcontracting_delivery_additional_value(self.doc)
        elif self.doc.purpose == "Return Raw Material to Customer":
            _set_return_raw_material_additional_value(self.doc)

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


def _set_subcontracting_delivery_additional_value(doc):
    """
    additional_taxable_value = SUM(received_items.rate * received_items.consumed_qty)
    """
    scio_details = [item.scio_detail for item in doc.items if item.get("scio_detail")]

    if not scio_details:
        return

    received_items = frappe.get_all(
        "Subcontracting Inward Order Received Item",
        filters={
            "scio_item_detail": ["in", scio_details],
            "is_customer_provided_item": 1,
        },
        fields=["scio_item_detail", "rate", "consumed_qty"],
    )

    if not received_items:
        return

    # Calculate total material cost per FG item
    fg_material_cost = defaultdict(float)
    for received_item in received_items:
        key = received_item.scio_item_detail
        cost = flt(received_item.rate) * flt(received_item.consumed_qty)
        fg_material_cost[key] += cost

    precision = doc.precision("additional_taxable_value", "taxes")

    # Set additional_taxable_value for each item
    for item in doc.items:
        if not item.get("scio_detail"):
            continue
        item.additional_taxable_value = flt(
            fg_material_cost.get(item.scio_detail), precision
        )


def _set_return_raw_material_additional_value(doc):
    """
    - additional_taxable_value = (SCIO Received Item rate * qty) - Stock Entry amount
    """
    scio_details = [item.scio_detail for item in doc.items if item.get("scio_detail")]

    if not scio_details:
        return

    received_items = frappe._dict(
        frappe.get_all(
            "Subcontracting Inward Order Received Item",
            filters={
                "name": ["in", scio_details],
            },
            fields=["name", "rate"],
            as_list=True,
        )
    )

    if not received_items:
        return

    precision = doc.precision("additional_taxable_value", "taxes")

    for item in doc.items:
        scio_detail = item.get("scio_detail")
        if not scio_detail:
            continue

        scio_rate = received_items.get(scio_detail)
        if not scio_rate:
            continue

        scio_value = flt(scio_rate) * flt(item.qty)
        item.additional_taxable_value = flt(scio_value - flt(item.amount), precision)
