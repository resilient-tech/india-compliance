import json

import frappe
from frappe import _
from frappe.contacts.doctype.address.address import get_default_address
from erpnext.controllers.taxes_and_totals import get_round_off_applicable_accounts

from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import (
    BillofEntry,
    update_gst_details,
)
from india_compliance.gst_india.overrides.ineligible_itc import update_valuation_rate
from india_compliance.gst_india.overrides.transaction import (
    get_gst_details,
    validate_charge_type_for_cess_non_advol_accounts,
)
from india_compliance.gst_india.utils import get_gst_accounts_by_type, is_api_enabled
from india_compliance.gst_india.utils.e_waybill import get_e_waybill_info


def onload(doc, method=None):
    if not doc.get("ewaybill"):
        return

    gst_settings = frappe.get_cached_doc("GST Settings")

    if not (
        is_api_enabled(gst_settings)
        and gst_settings.enable_e_waybill
        and gst_settings.enable_e_waybill_for_sc
    ):
        return

    doc.set_onload("e_waybill_info", get_e_waybill_info(doc))


def before_save(doc, method=None):
    update_gst_details(doc)


def before_submit(doc, method=None):
    update_gst_details(doc)


def validate(doc, method=None):
    # This has to be called after `amount` is updated based upon `additional_costs` in erpnext
    set_taxable_value(doc)
    set_taxes_and_totals(doc)

    validate_taxes(doc)
    update_valuation_rate(doc)


def set_taxes_and_totals(doc):
    set_item_wise_tax_rates(doc)
    set_total_taxes(doc)


def set_item_wise_tax_rates(doc, item_name=None, tax_name=None):
    items, taxes = BillofEntry.get_rows_to_update(doc, item_name, tax_name)
    tax_accounts = {tax.account_head for tax in taxes}

    if not tax_accounts:
        return

    tax_templates = {item.item_tax_template for item in items}
    item_tax_map = BillofEntry.get_item_tax_map(doc, tax_templates, tax_accounts)

    for tax in taxes:
        item_wise_tax_rates = (
            json.loads(tax.item_wise_tax_rates) if tax.item_wise_tax_rates else {}
        )

        for item in items:
            key = (item.item_tax_template, tax.account_head)
            item_wise_tax_rates[item.name] = item_tax_map.get(key, tax.rate)

        tax.item_wise_tax_rates = json.dumps(item_wise_tax_rates)


def set_total_taxes(doc):
    total_taxes = 0

    round_off_accounts = get_round_off_applicable_accounts(doc.company, [])
    for tax in doc.taxes:
        tax.tax_amount = BillofEntry.get_tax_amount(
            doc, tax.item_wise_tax_rates, tax.charge_type
        )

        if tax.account_head in round_off_accounts:
            tax.tax_amount = round(tax.tax_amount, 0)

        total_taxes += tax.tax_amount
        tax.base_tax_amount_after_discount_amount = total_taxes

    doc.total_taxes = total_taxes


@frappe.whitelist()
def update_party_details(party_details, doctype, company):
    party_details = frappe.parse_json(party_details)

    address = party_details.customer_address
    if not address:
        address = get_default_address("Supplier", party_details.get("supplier"))
        party_details.update(customer_address=address)

    # update gst details
    if address:
        party_details.update(
            frappe.db.get_value(
                "Address",
                address,
                ["gstin as billing_address_gstin"],
                as_dict=1,
            )
        )

    # Update address for update
    response = {
        "supplier_address": address,  # should be set first as gst_category and gstin is fetched from address
        **get_gst_details(party_details, doctype, company, update_place_of_supply=True),
    }

    return response


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

        if tax.account_head not in (output_accounts):
            frappe.throw(
                _("Row #{0}: Only Output accounts are allowed in {1}").format(
                    tax.idx, doc.doctype
                )
            )

        validate_charge_type_for_cess_non_advol_accounts(
            [output_accounts.cess_non_advol_account], tax
        )


def set_taxable_value(doc):
    for item in doc.items:
        item.taxable_value = item.amount