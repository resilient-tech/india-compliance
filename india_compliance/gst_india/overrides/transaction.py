import json

import frappe
from erpnext.controllers.accounts_controller import get_taxes_and_charges
from frappe import _

from ..utils import (get_gst_accounts, get_place_of_supply, get_tax_template,
                     get_tax_template_based_on_category, is_internal_transfer,
                     update_party_details)


def set_place_of_supply(doc, method=None):
    doc.place_of_supply = get_place_of_supply(doc, doc.doctype)


def get_itemised_tax_breakup_header(item_doctype, tax_accounts):
    hsn_wise_in_gst_settings = frappe.db.get_single_value(
        "GST Settings", "hsn_wise_tax_breakup"
    )
    if (
        frappe.get_meta(item_doctype).has_field("gst_hsn_code")
        and hsn_wise_in_gst_settings
    ):
        return [_("HSN/SAC"), _("Taxable Amount")] + tax_accounts
    else:
        return [_("Item"), _("Taxable Amount")] + tax_accounts


def get_itemised_tax_breakup_data(*args, **kwargs):
    from india_compliance.gst_india.utils import get_itemised_tax_breakup_data

    return get_itemised_tax_breakup_data(*args, **kwargs)


@frappe.whitelist()
def get_regional_round_off_accounts(company, account_list):
    country = frappe.get_cached_value("Company", company, "country")

    if country != "India":
        return

    if isinstance(account_list, str):
        account_list = json.loads(account_list)

    if not frappe.db.get_single_value("GST Settings", "round_off_gst_values"):
        return

    gst_accounts = get_gst_accounts(company)

    gst_account_list = []
    for account in ["cgst_account", "sgst_account", "igst_account"]:
        if account in gst_accounts:
            gst_account_list += gst_accounts.get(account)

    account_list.extend(gst_account_list)

    return account_list


@frappe.whitelist()
def get_regional_address_details(party_details, doctype, company):
    if isinstance(party_details, str):
        party_details = json.loads(party_details)
        party_details = frappe._dict(party_details)

    update_party_details(party_details, doctype)

    party_details.place_of_supply = get_place_of_supply(party_details, doctype)

    if is_internal_transfer(party_details, doctype):
        party_details.taxes_and_charges = ""
        party_details.taxes = []
        return party_details

    if doctype in ("Sales Invoice", "Delivery Note", "Sales Order"):
        master_doctype = "Sales Taxes and Charges Template"
        tax_template_by_category = get_tax_template_based_on_category(
            master_doctype, company, party_details
        )

    elif doctype in ("Purchase Invoice", "Purchase Order", "Purchase Receipt"):
        master_doctype = "Purchase Taxes and Charges Template"
        tax_template_by_category = get_tax_template_based_on_category(
            master_doctype, company, party_details
        )

    if tax_template_by_category:
        party_details["taxes_and_charges"] = tax_template_by_category
        return party_details

    if not party_details.place_of_supply:
        return party_details
    if not party_details.company_gstin:
        return party_details

    if (
        doctype in ("Sales Invoice", "Delivery Note", "Sales Order")
        and party_details.company_gstin
        and party_details.company_gstin[:2] != party_details.place_of_supply[:2]
    ) or (
        doctype in ("Purchase Invoice", "Purchase Order", "Purchase Receipt")
        and party_details.supplier_gstin
        and party_details.supplier_gstin[:2] != party_details.place_of_supply[:2]
    ):
        default_tax = get_tax_template(
            master_doctype, company, 1, party_details.company_gstin[:2]
        )
    else:
        default_tax = get_tax_template(
            master_doctype, company, 0, party_details.company_gstin[:2]
        )

    if not default_tax:
        return party_details

    party_details["taxes_and_charges"] = default_tax
    party_details.taxes = get_taxes_and_charges(master_doctype, default_tax)

    return party_details


def set_item_tax_from_hsn_code(item):
    if not item.taxes and item.gst_hsn_code:
        hsn_doc = frappe.get_doc("GST HSN Code", item.gst_hsn_code)

        for tax in hsn_doc.taxes:
            item.append(
                "taxes",
                {
                    "item_tax_template": tax.item_tax_template,
                    "tax_category": tax.tax_category,
                    "valid_from": tax.valid_from,
                },
            )


def validate_einvoice_fields(doc):
    from india_compliance.gst_india.utils.e_invoice import \
        validate_einvoice_fields

    return validate_einvoice_fields(doc)
