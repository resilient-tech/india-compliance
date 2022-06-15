import json

import frappe
from frappe import _, bold
from frappe.model.utils import get_fetch_values
from frappe.utils import cint, flt
from erpnext.controllers.accounts_controller import get_taxes_and_charges

from india_compliance.gst_india.constants import STATE_NUMBERS
from india_compliance.gst_india.utils import (
    get_all_gst_accounts,
    get_gst_accounts,
    get_gst_accounts_by_type,
    get_place_of_supply,
)


def update_taxable_values(doc, method=None):
    country = frappe.get_cached_value("Company", doc.company, "country")

    if country != "India":
        return

    gst_accounts = get_gst_accounts(doc.company)

    # fmt: off
    # Only considering sgst account to avoid inflating taxable value
    gst_account_list = gst_accounts.get("sgst_account", []) + gst_accounts.get("igst_account", [])

    # fmt: on
    additional_taxes = 0
    total_charges = 0
    item_count = 0
    considered_rows = []

    for tax in doc.get("taxes"):
        prev_row_id = cint(tax.row_id) - 1
        if tax.account_head in gst_account_list and prev_row_id not in considered_rows:
            if tax.charge_type == "On Previous Row Amount":
                additional_taxes += doc.get("taxes")[
                    prev_row_id
                ].tax_amount_after_discount_amount
                considered_rows.append(prev_row_id)
            if tax.charge_type == "On Previous Row Total":
                additional_taxes += (
                    doc.get("taxes")[prev_row_id].base_total - doc.base_net_total
                )
                considered_rows.append(prev_row_id)

    for item in doc.get("items"):
        proportionate_value = item.base_net_amount if doc.base_net_total else item.qty
        total_value = doc.base_net_total if doc.base_net_total else doc.total_qty

        applicable_charges = flt(
            flt(
                proportionate_value * (flt(additional_taxes) / flt(total_value)),
                item.precision("taxable_value"),
            )
        )
        item.taxable_value = applicable_charges + proportionate_value
        total_charges += applicable_charges
        item_count += 1

    if total_charges != additional_taxes:
        diff = additional_taxes - total_charges
        doc.get("items")[item_count - 1].taxable_value += diff


def is_indian_registered_company(doc):
    if not doc.company_gstin:
        country, gst_category = frappe.get_cached_value(
            "Company", doc.company, ("country", "gst_category")
        )

        if country != "India" or gst_category == "Unregistered":
            return False

    return True


def validate_mandatory_fields(doc, fields):
    for field in fields:
        if not doc.get(field):
            frappe.throw(
                _("{0} is a mandatory field for creating a GST Compliant {1}").format(
                    bold(_(doc.meta.get_label(field))),
                    (doc.doctype),
                )
            )


def validate_gst_accounts(doc):
    """
    Validate GST accounts before invoice creation
    - Only Output Accounts should be allowed in GST Sales Invoice
    - If supply made to SEZ/Overseas without payment of tax, then no GST account should be specified
    - SEZ supplies should not have CGST or SGST account
    - Inter-State supplies should not have CGST or SGST account
    - Intra-State supplies should not have IGST account
    """

    if not doc.taxes:
        return

    accounts_list = get_all_gst_accounts(doc.company)
    output_accounts = get_gst_accounts_by_type(doc.company, "Output")

    for row in doc.taxes:
        account_head = row.account_head

        if account_head not in accounts_list or not row.tax_amount:
            continue

        if doc.gst_category in ("SEZ", "Overseas") and not doc.is_export_with_gst:
            frappe.throw(
                _(
                    "Cannot charge GST in Row #{0} since export is without"
                    " payment of GST"
                ).format(row.idx)
            )

        if account_head not in output_accounts.values():
            frappe.throw(
                _(
                    "{0} is not an Output GST Account and cannot be used in Sales"
                    " Transactions."
                ).format(bold(account_head))
            )

        # Inter State supplies should not have CGST or SGST account
        if (
            doc.place_of_supply[:2] != doc.company_gstin[:2]
            or doc.gst_category == "SEZ"
        ):
            if account_head in (
                output_accounts.cgst_account,
                output_accounts.sgst_account,
            ):
                frappe.throw(
                    _(
                        "Row #{0}: Cannot charge CGST/SGST for inter-state supplies"
                    ).format(row.idx)
                )

        # Intra State supplies should not have IGST account
        elif account_head == output_accounts.igst_account:
            frappe.throw(
                _("Row #{0}: Cannot charge IGST for intra-state supplies").format(
                    row.idx
                )
            )


def validate_tax_accounts_for_non_gst(doc):
    """GST Tax Accounts should not be charged for Non GST Items"""
    accounts_list = get_all_gst_accounts(doc.company)

    for row in doc.taxes:
        if row.account_head in accounts_list and row.tax_amount:
            frappe.throw(
                _("Row #{0}: Cannot charge GST for Non GST Items").format(
                    row.idx, row.account_head
                ),
                title=_("Invalid Taxes"),
            )


def validate_items(doc):
    """Validate Items for a GST Compliant Invoice"""

    if not doc.items:
        return

    item_tax_templates = frappe._dict()
    items_with_duplicate_taxes = []
    non_gst_items = []
    has_gst_items = False

    for row in doc.items:
        # Collect data to validate that non-GST items are not used with GST items
        if row.is_non_gst:
            non_gst_items.append(row.idx)
            continue

        has_gst_items = True

        # Different Item Tax Templates should not be used for the same Item Code
        if row.item_code not in item_tax_templates:
            item_tax_templates[row.item_code] = row.item_tax_template
            continue

        if row.item_tax_template != item_tax_templates[row.item_code]:
            items_with_duplicate_taxes.append(bold(row.item_code))

    if not has_gst_items:
        validate_tax_accounts_for_non_gst(doc)
        return False

    if non_gst_items:
        frappe.throw(
            _(
                "Items not covered under GST cannot be clubbed with items for which GST"
                " is applicable. Please create another document for items in the"
                " following row numbers:<br>{0}"
            ).format(", ".join(bold(row_no) for row_no in non_gst_items)),
            title=_("Invalid Items"),
        )

    if items_with_duplicate_taxes:
        frappe.throw(
            _(
                "Cannot use different Item Tax Templates in different rows for"
                " following items:<br> {0}"
            ).format("<br>".join(items_with_duplicate_taxes)),
            title="Inconsistent Item Tax Templates",
        )


def set_place_of_supply(doc, method=None):
    doc.place_of_supply = get_place_of_supply(doc)


def validate_hsn_code(doc, method=None):
    validate_hsn_code, min_hsn_digits = frappe.get_cached_value(
        "GST Settings",
        "GST Settings",
        ("validate_hsn_code", "min_hsn_digits"),
    )

    if not validate_hsn_code:
        return

    missing_hsn = []
    invalid_hsn = []
    min_hsn_digits = int(min_hsn_digits)

    for item in doc.items:
        if not (hsn_code := item.get("gst_hsn_code")):
            if doc._action == "submit":
                invalid_hsn.append(str(item.idx))
            else:
                missing_hsn.append(str(item.idx))

        elif len(hsn_code) < min_hsn_digits:
            invalid_hsn.append(str(item.idx))

    if doc._action == "submit":
        if not invalid_hsn:
            return

        frappe.throw(
            _(
                "Please enter a valid HSN/SAC code for the following row numbers:"
                " <br>{0}"
            ).format(frappe.bold(", ".join(invalid_hsn)))
        )

    if missing_hsn:
        frappe.msgprint(
            _(
                "Please enter HSN/SAC code for the following row numbers: <br>{0}"
            ).format(frappe.bold(", ".join(missing_hsn)))
        )

    if invalid_hsn:
        frappe.msgprint(
            _(
                "HSN/SAC code should be at least {0} digits long for the following"
                " row numbers: <br>{1}"
            ).format(min_hsn_digits, frappe.bold(", ".join(invalid_hsn)))
        )


def validate_overseas_gst_category(doc, method=None):
    if doc.gst_category not in ("SEZ", "Overseas"):
        return

    overseas_enabled = frappe.get_cached_value(
        "GST Settings", "GST Settings", "enable_overseas_transactions"
    )

    if not overseas_enabled:
        frappe.throw(
            _(
                "GST Category cannot be set to {0} since it is disabled in GST Settings"
            ).format(frappe.bold(doc.gst_category))
        )

    if doc.doctype == "POS Invoice":
        frappe.throw(_("Cannot set GST Category to SEZ / Overseas in POS Invoice"))


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


def get_regional_round_off_accounts(company, account_list):
    country = frappe.get_cached_value("Company", company, "country")

    if country != "India":
        return

    if isinstance(account_list, str):
        account_list = json.loads(account_list)

    if not frappe.db.get_single_value("GST Settings", "round_off_gst_values"):
        return

    account_list.extend(get_all_gst_accounts(company))

    return account_list


@frappe.whitelist()
def get_regional_address_details(party_details, doctype, company):
    """
    This function does not check for permissions since it returns insensitive data
    based on already sensitive input (party details)

    Data returned:
     - place of supply (based on address name in party_details)
     - tax template
     - taxes in the tax template
    """

    party_details = frappe.parse_json(party_details)
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


def update_party_details(party_details, doctype):
    for address_field in [
        "shipping_address",
        "company_address",
        "supplier_address",
        "shipping_address_name",
        "customer_address",
    ]:
        if party_details.get(address_field):
            party_details.update(
                get_fetch_values(
                    doctype, address_field, party_details.get(address_field)
                )
            )


def is_internal_transfer(party_details, doctype):
    if doctype in ("Sales Invoice", "Delivery Note", "Sales Order"):
        destination_gstin = party_details.company_gstin
    elif doctype in ("Purchase Invoice", "Purchase Order", "Purchase Receipt"):
        destination_gstin = party_details.supplier_gstin

    if not destination_gstin or party_details.gstin:
        return False

    if party_details.gstin == destination_gstin:
        return True
    else:
        False


def get_tax_template_based_on_category(master_doctype, company, party_details):
    if not party_details.get("tax_category"):
        return

    default_tax = frappe.db.get_value(
        master_doctype,
        {"company": company, "tax_category": party_details.get("tax_category")},
        "name",
    )

    return default_tax


def get_tax_template(master_doctype, company, is_inter_state, state_code):
    tax_categories = frappe.get_all(
        "Tax Category",
        fields=["name", "is_inter_state", "gst_state"],
        filters={"is_inter_state": is_inter_state, "is_reverse_charge": 0},
    )

    default_tax = ""

    for tax_category in tax_categories:
        if STATE_NUMBERS.get(tax_category.gst_state) == state_code or (
            not default_tax and not tax_category.gst_state
        ):
            default_tax = frappe.db.get_value(
                master_doctype,
                {"company": company, "disabled": 0, "tax_category": tax_category.name},
                "name",
            )
    return default_tax


def validate_reverse_charge_transaction(doc, method):
    country = frappe.get_cached_value("Company", doc.company, "country")

    if country != "India":
        return

    base_gst_tax = 0
    base_reverse_charge_booked = 0

    if not doc.is_reverse_charge:
        return

    reverse_charge_accounts = get_gst_accounts_by_type(
        doc.company, "Reverse Charge"
    ).values()

    input_gst_accounts = get_gst_accounts_by_type(doc.company, "Input").values()

    for tax in doc.get("taxes"):
        if tax.account_head in input_gst_accounts:
            if tax.add_deduct_tax == "Add":
                base_gst_tax += tax.base_tax_amount_after_discount_amount
            else:
                base_gst_tax += tax.base_tax_amount_after_discount_amount
        elif tax.account_head in reverse_charge_accounts:
            if tax.add_deduct_tax == "Add":
                base_reverse_charge_booked += tax.base_tax_amount_after_discount_amount
            else:
                base_reverse_charge_booked += tax.base_tax_amount_after_discount_amount

    if base_gst_tax != base_reverse_charge_booked:
        msg = _("Booked reverse charge is not equal to applied tax amount")
        msg += "<br>"
        msg += _(
            "Please refer {gst_document_link} to learn more about how to setup and"
            " create reverse charge invoice"
        ).format(
            gst_document_link=(
                '<a href="https://docs.erpnext.com/docs/user/manual/en/regional/india/gst-setup">GST'
                " Documentation</a>"
            )
        )

        frappe.throw(msg)


def validate_sales_transaction(doc, method=None):
    if not is_indian_registered_company(doc):
        return False

    if validate_items(doc) is False:
        # If there are no GST items, then no need to proceed further
        return False

    set_place_of_supply(doc)

    if doc.doctype not in ("Quotation", "Sales Order"):
        update_taxable_values(doc)

    validate_mandatory_fields(doc, ("company_gstin",))
    validate_overseas_gst_category(doc)
    validate_gst_accounts(doc)
    validate_hsn_code(doc)
