import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt
from erpnext.controllers.taxes_and_totals import (
    get_round_off_applicable_accounts as fetch_round_off_accounts,
)

from india_compliance.gst_india.overrides.transaction import (
    ItemGSTTreatment,
)
from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.utils import get_all_gst_accounts

ALLOWED_TAX_DIFFERENCE = 1  # Allowable difference in tax amount due to rounding off


class ItemGSTDetails:
    FIELDMAP = {}

    def get(self, docs, doctype, company):
        """
        Return Item GST Details for a list of documents
        """
        self.get_item_defaults()
        self.set_tax_amount_precisions(doctype)

        response = frappe._dict()

        for doc in docs:
            self.doc = doc
            if not doc.get("items") or not doc.get("taxes"):
                continue

            # TODO: To Deprecate
            self.set_item_code_wise_tax_details()

            for item in doc.get("items"):
                response[item.name] = self.get_tax_detail_by_item_code(item)

        return response

    def update(self, doc):
        """
        Update Item GST Details for a single document
        """
        self.doc = doc
        if not self.doc.get("items"):
            return

        self.get_item_defaults()
        self.set_tax_amount_precisions(doc.doctype)

        # TODO: To Deprecate
        if self.dont_recompute_tax_is_set():
            self.set_item_code_wise_tax_details()
            self.update_tax_details_by_item_code()

        else:
            self.set_item_name_wise_tax_details()

        self.validate_item_gst_details()

    def get_item_defaults(self):
        item_defaults = frappe._dict(count=0)

        for row in GST_TAX_TYPES:
            item_defaults[f"{row}_rate"] = 0
            item_defaults[f"{row}_amount"] = 0

        self.item_defaults = item_defaults

    def set_item_name_wise_tax_details(self):
        """
        Update Item Tax Details

        Possible Exceptions Handled:
        - There could be more than one row for same account
        - Item count added to handle rounding errors
        """

        tax_differences = defaultdict(float)
        for tax_row in self.doc.taxes:
            if not self.is_gst_tax_row(tax_row):
                continue
            tax_type = tax_row.gst_tax_type
            tax_differences[tax_type] += tax_row.get(self.tax_amount_field(), 0)

        last_item_with_tax = None
        last_item_defaults = None

        for item in self.doc.get("items"):
            item_defaults = self.item_defaults.copy()
            tax_amount = 0

            for tax_row in self.doc.taxes:
                if not self.is_gst_tax_row(tax_row):
                    continue

                tax = tax_row.gst_tax_type
                tax_rate_field = f"{tax}_rate"
                tax_amount_field = f"{tax}_amount"

                old = self.get_tax_details(tax_row)
                old = frappe.parse_json(tax_row.get(self.tax_details_field(), "{}"))

                if self.get_item_key(item) not in old:
                    # Do not compute if Item is not present in Item table
                    # There can be difference in Item Table and Item Wise Tax Details
                    continue

                tax_rate = self.get_item_tax_rate(item, tax_row)
                tax_amount = self.get_item_tax_amount(item, tax_rate, tax)

                # cases when charge type == "Actual"
                if tax_amount and not tax_rate:
                    continue

                tax_differences[tax] -= tax_amount
                item_defaults[tax_rate_field] = tax_rate
                item_defaults[tax_amount_field] += tax_amount

            item.update(item_defaults)

            # update tax difference only for taxable items
            if tax_amount:
                last_item_with_tax = item
                last_item_defaults = item_defaults

        # Handle rounding errors
        if tax_differences and last_item_with_tax:
            for tax, tax_amount in tax_differences.items():
                last_item_defaults[f"{tax}_amount"] += flt(tax_amount, 5)

            for fieldname, value in last_item_defaults.items():
                last_item_with_tax.set(fieldname, value)

    def set_item_code_wise_tax_details(self):
        """
        Item Tax Details complied
        Example:
        {
            "Item Code 1": {
                "count": 2,
                "cgst_rate": 9,
                "cgst_amount": 18,
                "sgst_rate": 9,
                "sgst_amount": 18,
                ...
            },
            ...
        }

        Possible Exceptions Handled:
        - There could be more than one row for same account
        - Item count added to handle rounding errors
        """

        tax_details = frappe._dict()

        for row in self.doc.get("items"):
            key = self.get_item_key(row)

            if key not in tax_details:
                tax_details[key] = self.item_defaults.copy()

            tax_details[key]["count"] += 1

        for row in self.doc.taxes:
            if not self.is_gst_tax_row(row):
                continue

            tax = row.gst_tax_type
            tax_rate_field = f"{tax}_rate"
            tax_amount_field = f"{tax}_amount"

            old = json.loads(row.get(self.tax_details_field(), "{}"))

            tax_difference = row.base_tax_amount_after_discount_amount
            last_item_with_tax = None

            # update item taxes
            for item_name in old:
                if item_name not in tax_details:
                    # Do not compute if Item is not present in Item table
                    # There can be difference in Item Table and Item Wise Tax Details
                    continue

                item_taxes = tax_details[item_name]
                tax_rate = old[item_name].get("tax_rate")
                tax_amount = old[item_name].get("tax_amount")

                tax_difference -= tax_amount

                # cases when charge type == "Actual"
                if tax_amount and not tax_rate:
                    continue

                item_taxes[tax_rate_field] = tax_rate
                item_taxes[tax_amount_field] += tax_amount

                # update tax difference only for taxable items
                if tax_amount:
                    last_item_with_tax = item_taxes

            # Floating point errors
            tax_difference = flt(tax_difference, 5)

            # Handle rounding errors
            if tax_difference and last_item_with_tax:
                last_item_with_tax[tax_amount_field] += tax_difference

        self.item_tax_details = tax_details

    def update_tax_details_by_item_code(self):
        for item in self.doc.get("items"):
            item.update(self.get_tax_detail_by_item_code(item))

    def get_item_key(self, item):
        return item.name

    def get_tax_detail_by_item_code(self, item):
        """
        - get item_tax_detail as it is if
            - only one row exists for same item
            - it is the last item

        - If count is greater than 1,
            - Manually calculate tax_amount for item
            - Reduce item_tax_detail with
                - tax_amount
                - count
        """
        item_key = self.get_item_key(item)

        item_tax_detail = self.item_tax_details.get(item_key)
        if not item_tax_detail:
            return {}

        if item_tax_detail.count == 1:
            return item_tax_detail

        item_tax_detail["count"] -= 1

        # Handle rounding errors
        response = item_tax_detail.copy()
        for tax in GST_TAX_TYPES:
            if (tax_rate := item_tax_detail[f"{tax}_rate"]) == 0:
                continue

            tax_amount = self.get_item_tax_amount(item, tax_rate, tax)

            tax_amount_field = f"{tax}_amount"
            item_tax_detail[tax_amount_field] -= tax_amount

            response.update({tax_amount_field: tax_amount})

        return response

    def validate_item_gst_details(self):
        invalid_rows = defaultdict(list)

        for item in self.doc.get("items"):
            for tax in GST_TAX_TYPES:
                expected_amt = self.get_item_tax_amount(
                    item, item.get(f"{tax}_rate"), tax
                )

                diff = abs(item.get(f"{tax}_amount") - expected_amt)

                if diff > ALLOWED_TAX_DIFFERENCE:
                    invalid_rows[item.idx].append(tax.upper())

        if invalid_rows:
            msg = (
                _(
                    "GST amounts do not match the calculated values based on tax rates for the following Item rows:<br><br>"
                )
                + "<ul>"
            )
            for idx, fields in invalid_rows.items():
                msg += _(
                    "<li><strong>Row #{0}</strong>: {1} amount mismatch</li>"
                ).format(idx, ", ".join(fields))

            msg += "</ul>"

            frappe.throw(
                msg,
                title=_("Incorrect Item GST Details"),
            )

    def set_tax_amount_precisions(self, doctype):
        item_doctype = frappe.get_meta(doctype).get_field("items").options

        meta = frappe.get_meta(item_doctype)

        self.precision = frappe._dict()
        default_precision = cint(frappe.db.get_default("float_precision")) or 3

        for tax_type in GST_TAX_TYPES:
            fieldname = f"{tax_type}_amount"
            field = meta.get_field(fieldname)
            if not field:
                continue

            self.precision[fieldname] = field.precision or default_precision

    def dont_recompute_tax_is_set(self):
        for row in self.doc.taxes:
            if not self.is_gst_tax_row(row):
                continue

            if row.get("dont_recompute_tax"):
                return True

        return False

    def is_gst_tax_row(self, row):
        return (
            row.gst_tax_type
            and row.gst_tax_type in GST_TAX_TYPES
            and row.get(self.tax_details_field())
        )

    def get_item_tax_rate(self, item, tax_row):
        """
        Get item tax rate from item tax template
        """
        item_tax_rates = self.get_tax_details(tax_row)
        return item_tax_rates.get(item.name)

    def get_item_tax_amount(self, item, tax_rate, tax):
        precision = self.precision.get(f"{tax}_amount")
        multiplier = item.qty if tax == "cess_non_advol" else item.taxable_value / 100

        return flt(tax_rate * multiplier, precision)

    def get_tax_details(self, tax_row):
        if not getattr(tax_row, "__tax_details", None):
            tax_row.__tax_details = frappe.parse_json(
                tax_row.get(self.tax_details_field()) or "{}"
            )

        return tax_row.__tax_details

    @staticmethod
    def tax_amount_field():
        return "tax_amount"

    @staticmethod
    def tax_details_field():
        return "item_wise_tax_rates"


def update_gst_details(doc, method=None):
    # TODO: add item tax template validation post exclude from GST
    ItemGSTTreatment().set(doc)
    ItemGSTDetails().update(doc)


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
