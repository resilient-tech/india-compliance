import json

import frappe
from frappe import _, bold
from frappe.model import delete_doc
from frappe.utils import cint, flt
from erpnext.controllers.accounts_controller import get_taxes_and_charges

from india_compliance.gst_india.constants import (
    OVERSEAS_GST_CATEGORIES,
    SALES_DOCTYPES,
    STATE_NUMBERS,
)
from india_compliance.gst_india.utils import (
    get_all_gst_accounts,
    get_gst_accounts_by_type,
    get_place_of_supply,
    validate_gst_category,
)

DOCTYPES_WITH_TAXABLE_VALUE = {
    "Purchase Invoice",
    "Delivery Note",
    "Sales Invoice",
    "POS Invoice",
}


def update_taxable_values(doc, valid_accounts):
    if doc.doctype not in DOCTYPES_WITH_TAXABLE_VALUE:
        return

    total_charges = 0
    apportioned_charges = 0

    if doc.taxes:
        if any(
            row
            for row in doc.taxes
            if row.tax_amount and row.account_head in valid_accounts
        ):
            reference_row_index = next(
                (
                    cint(row.row_id) - 1
                    for row in doc.taxes
                    if row.tax_amount
                    and row.charge_type == "On Previous Row Total"
                    and row.account_head in valid_accounts
                ),
                None,
            )

        else:
            reference_row_index = -1

        if reference_row_index is not None:
            total_charges = (
                doc.taxes[reference_row_index].base_total - doc.base_net_total
            )

    # base net total may be zero if invoice has zero rated items + shipping
    total_value = doc.base_net_total if doc.base_net_total else doc.total_qty

    if not total_value:
        return

    for item in doc.items:
        item.taxable_value = item.base_net_amount

        if not total_charges:
            continue

        proportionate_value = item.base_net_amount if doc.base_net_total else item.qty

        applicable_charges = flt(
            proportionate_value * (total_charges / total_value),
            item.precision("taxable_value"),
        )

        item.taxable_value += applicable_charges
        apportioned_charges += applicable_charges

    if apportioned_charges != total_charges:
        item.taxable_value += total_charges - apportioned_charges


def is_indian_registered_company(doc):
    if not doc.company_gstin:
        country, gst_category = frappe.get_cached_value(
            "Company", doc.company, ("country", "gst_category")
        )

        if country != "India" or gst_category == "Unregistered":
            return False

    return True


def validate_mandatory_fields(doc, fields, message=None):
    if isinstance(fields, str):
        fields = (fields,)

    for field in fields:
        if not doc.get(field):
            error_message = _("{0} is a mandatory field for GST Transactions").format(
                bold(_(doc.meta.get_label(field))),
            )

            if message:
                error_message += f". {message}"

            frappe.throw(error_message, title=_("Missing Required Field"))


def get_valid_accounts(company, is_sales_transaction=False):
    all_valid_accounts = []
    intra_state_accounts = []
    inter_state_accounts = []

    def add_to_valid_accounts(account_type):
        accounts = get_gst_accounts_by_type(company, account_type)
        all_valid_accounts.extend(accounts.values())
        intra_state_accounts.append(accounts.cgst_account)
        intra_state_accounts.append(accounts.sgst_account)
        inter_state_accounts.append(accounts.igst_account)

    if is_sales_transaction:
        add_to_valid_accounts("Output")
    else:
        add_to_valid_accounts("Input")
        add_to_valid_accounts("Reverse Charge")

    return all_valid_accounts, intra_state_accounts, inter_state_accounts


def validate_gst_accounts(doc, is_sales_transaction=False):
    """
    Validate GST accounts
    - Only Valid Accounts should be allowed
    - If export is made without GST, then no GST account should be specified
    - SEZ / Inter-State supplies should not have CGST or SGST account
    - Intra-State supplies should not have IGST account
    """

    if not doc.taxes:
        return

    if not (
        rows_to_validate := [
            row
            for row in doc.taxes
            if row.tax_amount and row.account_head in get_all_gst_accounts(doc.company)
        ]
    ):
        return

    # Helper functions

    def _get_matched_idx(rows_to_search, account_head_list):
        return next(
            (
                row.idx
                for row in rows_to_search
                if row.account_head in account_head_list
            ),
            None,
        )

    def _throw(message, title=None):
        frappe.throw(message, title=title or _("Invalid GST Account"))

    all_valid_accounts, intra_state_accounts, inter_state_accounts = get_valid_accounts(
        doc.company, is_sales_transaction
    )

    # Sales / Purchase Validations

    if is_sales_transaction:
        if is_export_without_payment_of_gst(doc) and (
            idx := _get_matched_idx(rows_to_validate, all_valid_accounts)
        ):
            _throw(
                _(
                    "Cannot charge GST in Row #{0} since export is without"
                    " payment of GST"
                ).format(idx)
            )

        if doc.get("is_reverse_charge") and (
            idx := _get_matched_idx(rows_to_validate, all_valid_accounts)
        ):
            _throw(
                _(
                    "Cannot charge GST in Row #{0} since supply is under reverse charge"
                ).format(idx)
            )

    elif doc.gst_category == "Registered Composition" and (
        idx := _get_matched_idx(rows_to_validate, all_valid_accounts)
    ):
        _throw(
            _(
                "Cannot claim Input GST in Row #{0} since purchase is being made from a"
                " dealer registered under Composition Scheme"
            ).format(idx)
        )

    elif not doc.is_reverse_charge:
        if idx := _get_matched_idx(
            rows_to_validate,
            get_gst_accounts_by_type(doc.company, "Reverse Charge").values(),
        ):
            _throw(
                _(
                    "Cannot use Reverse Charge Account in Row #{0} since purchase is"
                    " without Reverse Charge"
                ).format(idx)
            )

        if not doc.supplier_gstin and (
            idx := _get_matched_idx(rows_to_validate, all_valid_accounts)
        ):
            _throw(
                _(
                    "Cannot charge GST in Row #{0} since purchase is from a Supplier"
                    " without GSTIN"
                ).format(idx)
            )

    is_inter_state = is_inter_state_supply(doc)
    previous_row_references = set()

    for row in rows_to_validate:
        account_head = row.account_head

        if account_head not in all_valid_accounts:
            _throw(
                _("{0} is not a valid GST account for this transaction").format(
                    bold(account_head)
                ),
            )

        # Inter State supplies should not have CGST or SGST account
        if is_inter_state:
            if account_head in intra_state_accounts:
                _throw(
                    _(
                        "Row #{0}: Cannot charge CGST/SGST for inter-state supplies"
                    ).format(row.idx),
                )

        # Intra State supplies should not have IGST account
        elif account_head in inter_state_accounts:
            _throw(
                _("Row #{0}: Cannot charge IGST for intra-state supplies").format(
                    row.idx
                ),
            )

        if row.charge_type == "On Previous Row Amount":
            _throw(
                _(
                    "Row #{0}: Charge Type cannot be <strong>On Previous Row"
                    " Amount</strong> for a GST Account"
                ).format(row.idx),
                title=_("Invalid Charge Type"),
            )

        if row.charge_type == "On Previous Row Total":
            previous_row_references.add(row.row_id)

    if len(previous_row_references) > 1:
        _throw(
            _(
                "Only one row can be selected as a Reference Row for GST Accounts with"
                " Charge Type <strong>On Previous Row Total</strong>"
            ),
            title=_("Invalid Reference Row"),
        )

    return all_valid_accounts


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
    if not doc.place_of_supply:
        doc.place_of_supply = get_place_of_supply(doc, doc.doctype)


def is_inter_state_supply(doc):
    return doc.gst_category == "SEZ" or (
        doc.place_of_supply[:2] != get_source_state_code(doc)
    )


def get_source_state_code(doc):
    """
    Get the state code of the state from which goods / services are being supplied.
    Logic opposite to that of utils.get_place_of_supply
    """

    if doc.doctype in SALES_DOCTYPES:
        return doc.company_gstin[:2]

    if doc.gst_category == "Overseas":
        return "96"

    if doc.gst_category == "Unregistered" and doc.supplier_address:
        return frappe.db.get_value(
            "Address",
            doc.supplier_address,
            "gst_state_number",
        )

    return (doc.supplier_gstin or doc.company_gstin)[:2]


def validate_hsn_codes(doc, method=None):
    validate_hsn_code, min_hsn_digits = frappe.get_cached_value(
        "GST Settings",
        "GST Settings",
        ("validate_hsn_code", "min_hsn_digits"),
    )

    if not validate_hsn_code:
        return

    rows_with_missing_hsn = []
    rows_with_invalid_hsn = []
    min_hsn_digits = int(min_hsn_digits)

    for item in doc.items:
        if not (hsn_code := item.get("gst_hsn_code")):
            rows_with_missing_hsn.append(str(item.idx))

        elif len(hsn_code) < min_hsn_digits:
            rows_with_invalid_hsn.append(str(item.idx))

    if doc._action == "submit":
        # Same error for erroneous rows on submit
        rows_with_invalid_hsn += rows_with_missing_hsn

        if not rows_with_invalid_hsn:
            return

        frappe.throw(
            _(
                "Please enter a valid HSN/SAC code for the following row numbers:"
                " <br>{0}"
            ).format(frappe.bold(", ".join(rows_with_invalid_hsn)))
        )

    if rows_with_missing_hsn:
        frappe.msgprint(
            _(
                "Please enter HSN/SAC code for the following row numbers: <br>{0}"
            ).format(frappe.bold(", ".join(rows_with_missing_hsn)))
        )

    if rows_with_invalid_hsn:
        frappe.msgprint(
            _(
                "HSN/SAC code should be at least {0} digits long for the following"
                " row numbers: <br>{1}"
            ).format(min_hsn_digits, frappe.bold(", ".join(rows_with_invalid_hsn)))
        )


def validate_overseas_gst_category(doc, method=None):
    if doc.gst_category not in OVERSEAS_GST_CATEGORIES:
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


def update_party_details(party_details, doctype, company):
    party_details.update(
        get_gst_details(party_details, doctype, company, update_place_of_supply=True)
    )


@frappe.whitelist()
def get_gst_details(party_details, doctype, company, *, update_place_of_supply=False):
    """
    This function does not check for permissions since it returns insensitive data
    based on already sensitive input (party details)

    Data returned:
     - place of supply (based on address name in party_details)
     - tax template
     - taxes in the tax template
    """

    is_sales_transaction = doctype in SALES_DOCTYPES

    if isinstance(party_details, str):
        party_details = frappe.parse_json(party_details)

    gst_details = frappe._dict()

    party_address_field = (
        "customer_address" if is_sales_transaction else "supplier_address"
    )
    if not party_details.get(party_address_field):
        party_gst_details = get_party_gst_details(party_details, is_sales_transaction)

        # updating party details to get correct place of supply
        if party_gst_details:
            party_details.update(party_gst_details)
            gst_details.update(party_gst_details)

    gst_details.place_of_supply = (
        party_details.place_of_supply
        if (not update_place_of_supply and party_details.place_of_supply)
        else get_place_of_supply(party_details, doctype)
    )

    if is_sales_transaction:
        source_gstin = party_details.company_gstin
        destination_gstin = party_details.billing_address_gstin
    else:
        source_gstin = party_details.supplier_gstin
        destination_gstin = party_details.company_gstin

    if (
        (destination_gstin and destination_gstin == source_gstin)  # Internal transfer
        or (
            is_sales_transaction
            and (
                is_export_without_payment_of_gst(party_details)
                or party_details.is_reverse_charge
            )
        )
        or (
            not is_sales_transaction
            and (
                party_details.gst_category == "Registered Composition"
                or (
                    not party_details.is_reverse_charge
                    and not party_details.supplier_gstin
                )
            )
        )
    ):
        # GST Not Applicable
        gst_details.taxes_and_charges = ""
        gst_details.taxes = []
        return gst_details

    master_doctype = (
        "Sales Taxes and Charges Template"
        if is_sales_transaction
        else "Purchase Taxes and Charges Template"
    )

    tax_template_by_category = get_tax_template_based_on_category(
        master_doctype, company, party_details
    )

    if tax_template_by_category:
        gst_details.taxes_and_charges = tax_template_by_category
        gst_details.taxes = get_taxes_and_charges(
            master_doctype, tax_template_by_category
        )
        return gst_details

    if not gst_details.place_of_supply or not party_details.company_gstin:
        return gst_details

    if default_tax := get_tax_template(
        master_doctype,
        company,
        is_inter_state_supply(
            party_details.copy().update(
                doctype=doctype,
                place_of_supply=gst_details.place_of_supply,
            )
        ),
        party_details.company_gstin[:2],
    ):
        gst_details.taxes_and_charges = default_tax
        gst_details.taxes = get_taxes_and_charges(master_doctype, default_tax)

    return gst_details


def get_party_gst_details(party_details, is_sales_transaction):
    """fetch GSTIN and GST category from party"""

    party_type = "Customer" if is_sales_transaction else "Supplier"
    gstin_fieldname = (
        "billing_address_gstin" if is_sales_transaction else "supplier_gstin"
    )

    if not (party := party_details.get(party_type.lower())):
        return

    return frappe.db.get_value(
        party_type,
        party,
        ("gst_category", f"gstin as {gstin_fieldname}"),
        as_dict=True,
    )


def get_tax_template_based_on_category(master_doctype, company, party_details):
    if not party_details.tax_category:
        return

    default_tax = frappe.db.get_value(
        master_doctype,
        {"company": company, "tax_category": party_details.tax_category},
        "name",
    )

    return default_tax


def get_tax_template(master_doctype, company, is_inter_state, state_code):
    tax_categories = frappe.get_all(
        "Tax Category",
        fields=["name", "is_inter_state", "gst_state"],
        filters={
            "is_inter_state": 1 if is_inter_state else 0,
            "is_reverse_charge": 0,
            "disabled": 0,
        },
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


def validate_reverse_charge_transaction(doc, method=None):
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

    doc.eligibility_for_itc = "ITC on Reverse Charge"


def is_export_without_payment_of_gst(doc):
    return doc.gst_category in OVERSEAS_GST_CATEGORIES and not doc.is_export_with_gst


def validate_transaction(doc, method=None):
    if not is_indian_registered_company(doc) or doc.get("is_opening") == "Yes":
        return False

    if validate_items(doc) is False:
        # If there are no GST items, then no need to proceed further
        return False

    set_place_of_supply(doc)
    validate_mandatory_fields(doc, ("company_gstin", "place_of_supply"))
    validate_mandatory_fields(
        doc, "gst_category", _("Please ensure it is set in the Party and / or Address.")
    )
    validate_overseas_gst_category(doc)

    if is_sales_transaction := doc.doctype in SALES_DOCTYPES:
        validate_hsn_codes(doc)
    else:
        validate_reverse_charge_transaction(doc)

    validate_gst_category(
        doc.gst_category,
        doc.billing_address_gstin if is_sales_transaction else doc.supplier_gstin,
    )

    valid_accounts = validate_gst_accounts(doc, is_sales_transaction) or ()
    update_taxable_values(doc, valid_accounts)


# Note: This is kept for backwards compatibility with Frappe versions < 14.21.0
def ignore_logs_on_trash(doc, method=None):
    if (
        not hasattr(delete_doc, "doctypes_to_skip")
        or "e-Waybill Log" in delete_doc.doctypes_to_skip
    ):
        return

    delete_doc.doctypes_to_skip += (
        "e-Waybill Log",
        "e-Invoice Log",
    )
