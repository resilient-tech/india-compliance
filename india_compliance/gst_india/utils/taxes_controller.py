import json

import frappe
from erpnext.controllers.taxes_and_totals import (
    get_round_off_applicable_accounts as fetch_round_off_accounts,
)
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils.data import flt

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
def set_item_wise_tax_rates(doc: str, item_name: str | None = None, tax_name: str | None = None):
    """
    Permission check not required as it processes client-provided data.
    """
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

            item_wise_tax_rates = json.loads(tax.item_wise_tax_rates) if tax.item_wise_tax_rates else {}

            for item in items:
                key = f"{item.item_tax_template},{tax.account_head}"
                item_wise_tax_rates[item.name] = item_tax_map.get(key, tax.rate)

            tax.item_wise_tax_rates = json.dumps(item_wise_tax_rates)

        return taxes

    def update_item_taxable_value(self):
        for item in self.doc.get("items"):
            taxable_value = self.get_value("amount", item)
            taxable_value += flt(item.get("additional_taxable_value", 0), item.precision("taxable_value"))

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
        round_off_accounts = fetch_round_off_accounts(self.doc.company, [], self.doc)

        for tax in self.doc.taxes:
            if tax.charge_type == "Actual":
                continue

            tax.tax_amount = self.get_tax_amount(tax.item_wise_tax_rates, tax.charge_type)

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
        items = self.doc.get("items", {"name": item_name}) if item_name else self.doc.get("items")
        taxes = self.doc.get("taxes", {"name": tax_name}) if tax_name else self.doc.taxes

        return items, taxes

    def get_tax_amount(self, item_wise_tax_rates, charge_type):
        if isinstance(item_wise_tax_rates, str):
            item_wise_tax_rates = json.loads(item_wise_tax_rates)

        tax_amount = 0
        for item in self.doc.get("items"):
            multiplier = item.qty if charge_type == "On Item Quantity" else item.taxable_value / 100
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
            frappe.throw(_("Row #{0}: Only GST accounts are allowed in {1}.").format(tax.idx, doc.doctype))


def _set_subcontracting_delivery_additional_value(doc):
    """
    For Subcontracting Delivery (job worker delivering finished goods to the
    customer), taxable value must include the value of customer-provided raw
    materials consumed, apportioned by weighted-average actual consumption
    (as per CAS-4; process loss is absorbed by good units):

        additional_taxable_value =
            SUM(received_item.rate * received_item.consumed_qty)
            / scio_item.produced_qty
            * item.qty

    consumed_qty and produced_qty are both cumulative, so each delivery is
    valued at the weighted-average-to-date.

    Rows are left at 0 when:
    - scio_detail does not reference a Subcontracting Inward Order Item
      (eg. secondary items reference SCIO Secondary Item)
    - no customer-provided material has been consumed for the finished good
    - produced_qty is 0 (warned via msgprint)
    """
    scio_details = {item.scio_detail for item in doc.items if item.get("scio_detail")}

    if not scio_details:
        return

    scio_item = frappe.qb.DocType("Subcontracting Inward Order Item")
    received_item = frappe.qb.DocType("Subcontracting Inward Order Received Item")

    fg_costs = {
        row.name: row
        for row in (
            frappe.qb.from_(scio_item)
            .join(received_item)
            .on(
                (received_item.reference_name == scio_item.name)
                & (received_item.is_customer_provided_item == 1)
            )
            .select(
                scio_item.name,
                scio_item.produced_qty,
                Sum(received_item.rate * received_item.consumed_qty).as_("material_cost"),
            )
            .where(scio_item.name.isin(list(scio_details)))
            .groupby(scio_item.name)
            .run(as_dict=True)
        )
    }

    if not fg_costs:
        return

    precision = doc.precision("additional_taxable_value", "items")
    rows_without_produced_qty = []

    for item in doc.items:
        fg_cost = fg_costs.get(item.get("scio_detail"))
        if not fg_cost or not fg_cost.material_cost:
            continue

        if not fg_cost.produced_qty:
            rows_without_produced_qty.append(item.idx)
            continue

        item.additional_taxable_value = flt(
            flt(fg_cost.material_cost) / flt(fg_cost.produced_qty) * flt(item.qty), precision
        )

    if rows_without_produced_qty:
        frappe.msgprint(
            _(
                "Row #{0}: Value of customer-provided materials could not be added to the"
                " taxable value as no production has been reported yet"
            ).format(", ".join(map(str, rows_without_produced_qty))),
            alert=True,
            indicator="yellow",
        )


def _set_return_raw_material_additional_value(doc):
    """
    For raw material returns, taxable value must equal the customer's declared
    value (SCIO Received Item rate * qty) as required on the Delivery Challan
    (Rule 55). The adjustment MAY be negative - it corrects the Stock Entry
    amount (valuation) down/up to the declared value:

        additional_taxable_value = (rate * item.qty) - item.amount
    """
    scio_details = {item.scio_detail for item in doc.items if item.get("scio_detail")}

    if not scio_details:
        return

    declared_rates = frappe._dict(
        frappe.get_all(
            "Subcontracting Inward Order Received Item",
            filters={"name": ("in", list(scio_details)), "is_customer_provided_item": 1},
            fields=["name", "rate"],
            as_list=True,
        )
    )

    if not declared_rates:
        return

    precision = doc.precision("additional_taxable_value", "items")

    for item in doc.items:
        if (scio_detail := item.get("scio_detail")) not in declared_rates:
            continue

        declared_value = flt(declared_rates[scio_detail]) * flt(item.qty)
        item.additional_taxable_value = flt(declared_value - flt(item.amount), precision)
