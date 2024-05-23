import json
from collections import defaultdict

import frappe
from frappe import _, bold
from frappe.utils import cint, flt
from erpnext.controllers.accounts_controller import get_taxes_and_charges

from india_compliance.gst_india.constants import (
    GST_TAX_TYPES,
    SALES_DOCTYPES,
    STATE_NUMBERS,
)
from india_compliance.gst_india.constants.custom_fields import E_WAYBILL_INV_FIELDS
from india_compliance.gst_india.doctype.gstin.gstin import (
    _validate_gst_transporter_id_info,
    _validate_gstin_info,
    get_gstin_status,
)
from india_compliance.gst_india.utils import (
    get_all_gst_accounts,
    get_gst_accounts_by_tax_type,
    get_gst_accounts_by_type,
    get_hsn_settings,
    get_place_of_supply,
    get_place_of_supply_options,
    is_overseas_doc,
    join_list_with_custom_separators,
    validate_gst_category,
    validate_gstin,
)
from india_compliance.income_tax_india.overrides.tax_withholding_category import (
    get_tax_withholding_accounts,
)

DOCTYPES_WITH_GST_DETAIL = {
    "Supplier Quotation",
    "Purchase Order",
    "Purchase Receipt",
    "Purchase Invoice",
    "Quotation",
    "Sales Order",
    "Delivery Note",
    "Sales Invoice",
    "POS Invoice",
}


def set_gst_breakup(doc):
    gst_breakup_html = frappe.render_template(
        "templates/gst_breakup.html", dict(doc=doc)
    )
    if not gst_breakup_html:
        return

    doc.gst_breakup_table = gst_breakup_html.replace("\n", "").replace("    ", "")


def update_taxable_values(doc, valid_accounts):
    if doc.doctype not in DOCTYPES_WITH_GST_DETAIL:
        return

    total_charges = 0
    apportioned_charges = 0
    tax_witholding_amount = 0

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
                None,  # ignore accounts after GST accounts
            )

        else:
            # If no GST account is used
            reference_row_index = -1
            tax_witholding_amount = get_tds_amount(doc)

        if reference_row_index is not None:
            total_charges = (
                doc.taxes[reference_row_index].base_total
                - doc.base_net_total
                - tax_witholding_amount
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


def validate_item_wise_tax_detail(doc, gst_accounts):
    if doc.doctype not in DOCTYPES_WITH_GST_DETAIL:
        return

    item_taxable_values = defaultdict(float)
    item_qty_map = defaultdict(float)

    cess_non_advol_account = get_gst_accounts_by_tax_type(doc.company, "cess_non_advol")

    for row in doc.items:
        item_key = row.item_code or row.item_name
        item_taxable_values[item_key] += row.taxable_value
        item_qty_map[item_key] += row.qty

    for row in doc.taxes:
        if row.account_head not in gst_accounts:
            continue

        if row.charge_type != "Actual":
            continue

        item_wise_tax_detail = frappe.parse_json(row.item_wise_tax_detail or "{}")

        for item_name, (tax_rate, tax_amount) in item_wise_tax_detail.items():
            if tax_amount and not tax_rate:
                frappe.throw(
                    _(
                        "Tax Row #{0}: Charge Type is set to Actual. However, this would"
                        " not compute item taxes, and your further reporting will be affected."
                    ).format(row.idx),
                    title=_("Invalid Charge Type"),
                )

            # Sales Invoice is created with manual tax amount. So, when a sales return is created,
            # the tax amount is not recalculated, causing the issue.

            is_cess_non_advol = row.account_head in cess_non_advol_account
            multiplier = (
                item_qty_map.get(item_name, 0)
                if is_cess_non_advol
                else item_taxable_values.get(item_name, 0) / 100
            )
            tax_difference = abs(multiplier * tax_rate - tax_amount)

            if tax_difference > 1:
                correct_charge_type = (
                    "On Item Quantity" if is_cess_non_advol else "On Net Total"
                )

                frappe.throw(
                    _(
                        "Tax Row #{0}: Charge Type is set to Actual. However, Tax Amount {1} as computed for Item {2}"
                        " is incorrect. Try setting the Charge Type to {3}"
                    ).format(row.idx, tax_amount, bold(item_name), correct_charge_type)
                )


def get_tds_amount(doc):
    tds_accounts = get_tax_withholding_accounts(doc.company)
    tds_amount = 0
    for row in doc.taxes:
        if row.account_head not in tds_accounts:
            continue

        if row.get("add_deduct_tax") and row.add_deduct_tax == "Deduct":
            tds_amount -= row.tax_amount

        else:
            tds_amount += row.tax_amount

    return tds_amount


def is_indian_registered_company(doc):
    if not doc.get("company_gstin"):
        country, gst_category = frappe.get_cached_value(
            "Company", doc.company, ("country", "gst_category")
        )

        if country != "India" or gst_category == "Unregistered":
            return False

    return True


def validate_mandatory_fields(doc, fields, error_message=None):
    if isinstance(fields, str):
        fields = (fields,)

    if not error_message:
        error_message = _("{0} is a mandatory field for GST Transactions")

    for field in fields:
        if doc.get(field):
            continue

        if doc.flags.ignore_mandatory:
            return False

        frappe.throw(
            error_message.format(bold(_(doc.meta.get_label(field)))),
            title=_("Missing Required Field"),
        )


def get_applicable_gst_accounts(
    company, *, for_sales, is_inter_state, is_reverse_charge=False
):
    all_gst_accounts = set()
    applicable_gst_accounts = set()

    if for_sales:
        account_types = ["Output"]
    else:
        account_types = ["Input"]

    if is_reverse_charge:
        account_types.append("Reverse Charge")

    for account_type in account_types:
        accounts = get_gst_accounts_by_type(company, account_type, throw=True)

        if not accounts:
            continue

        for account_type, account_name in accounts.items():
            if not account_name:
                continue

            if is_inter_state and account_type in ["cgst_account", "sgst_account"]:
                all_gst_accounts.add(account_name)
                continue

            if not is_inter_state and account_type == "igst_account":
                all_gst_accounts.add(account_name)
                continue

            applicable_gst_accounts.add(account_name)
            all_gst_accounts.add(account_name)

    return all_gst_accounts, applicable_gst_accounts


@frappe.whitelist()
def get_valid_gst_accounts(company):
    frappe.has_permission("Item Tax Template", "read", throw=True)
    return get_valid_accounts(company, for_sales=True, for_purchase=True, throw=False)


def get_valid_accounts(company, *, for_sales=False, for_purchase=False, throw=True):
    all_valid_accounts = []
    intra_state_accounts = []
    inter_state_accounts = []

    account_types = []
    if for_sales:
        account_types.append("Output")

    if for_purchase:
        account_types.extend(["Input", "Reverse Charge"])

    for account_type in account_types:
        accounts = get_gst_accounts_by_type(company, account_type, throw=throw)
        if not accounts:
            continue

        all_valid_accounts.extend(accounts.values())
        intra_state_accounts.append(accounts.cgst_account)
        intra_state_accounts.append(accounts.sgst_account)
        inter_state_accounts.append(accounts.igst_account)

    return all_valid_accounts, intra_state_accounts, inter_state_accounts


def validate_gst_accounts(doc, is_sales_transaction=False):
    """
    Validate GST accounts
    - Only Valid Accounts should be allowed
    - No GST account should be specified for transactions where Company GSTIN = Party GSTIN
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
        doc.company,
        for_sales=is_sales_transaction,
        for_purchase=not is_sales_transaction,
    )
    cess_non_advol_accounts = get_gst_accounts_by_tax_type(
        doc.company, "cess_non_advol"
    )

    # Company GSTIN = Party GSTIN
    party_gstin = (
        doc.billing_address_gstin if is_sales_transaction else doc.supplier_gstin
    )
    if (
        party_gstin
        and doc.company_gstin == party_gstin
        and (idx := _get_matched_idx(rows_to_validate, all_valid_accounts))
    ):
        _throw(
            _(
                "Cannot charge GST in Row #{0} since Company GSTIN and Party GSTIN are"
                " same"
            ).format(idx)
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

        # validating charge type "On Item Quantity" and non_cess_advol_account
        validate_charge_type_for_cess_non_advol_accounts(cess_non_advol_accounts, row)

    used_accounts = set(row.account_head for row in rows_to_validate)
    if not is_inter_state:
        if used_accounts and not set(intra_state_accounts[:2]).issubset(used_accounts):
            _throw(
                _(
                    "Cannot use only one of CGST or SGST account for intra-state"
                    " supplies"
                ),
                title=_("Invalid GST Accounts"),
            )

    if len(previous_row_references) > 1:
        _throw(
            _(
                "Only one row can be selected as a Reference Row for GST Accounts with"
                " Charge Type <strong>On Previous Row Total</strong>"
            ),
            title=_("Invalid Reference Row"),
        )

    for row in doc.get("items") or []:
        if not row.item_tax_template:
            continue

        for account in used_accounts:
            if account in row.item_tax_rate:
                continue

            frappe.msgprint(
                _(
                    "Item Row #{0}: GST Account {1} is missing in Item Tax Template {2}"
                ).format(row.idx, bold(account), bold(row.item_tax_template)),
                title=_("Invalid Item Tax Template"),
                indicator="orange",
            )

    return all_valid_accounts


def validate_charge_type_for_cess_non_advol_accounts(cess_non_advol_accounts, tax_row):
    if (
        tax_row.charge_type == "On Item Quantity"
        and tax_row.account_head not in cess_non_advol_accounts
    ):
        frappe.throw(
            _(
                "Row #{0}: Charge Type cannot be <strong>On Item Quantity</strong>"
                " as it is not a Cess Non Advol Account"
            ).format(tax_row.idx),
            title=_("Invalid Charge Type"),
        )

    if (
        tax_row.charge_type not in ["On Item Quantity", "Actual"]
        and tax_row.account_head in cess_non_advol_accounts
    ):
        frappe.throw(
            _(
                "Row #{0}: Charge Type must be <strong>On Item Quantity / Actual</strong>"
                " as it is a Cess Non Advol Account"
            ).format(tax_row.idx),
            title=_("Invalid Charge Type"),
        )


def validate_items(doc):
    """Validate Items for a GST Compliant Invoice"""

    if not doc.get("items"):
        return

    item_tax_templates = frappe._dict()
    items_with_duplicate_taxes = []

    for row in doc.items:
        # Different Item Tax Templates should not be used for the same Item Code
        if row.item_code not in item_tax_templates:
            item_tax_templates[row.item_code] = row.item_tax_template
            continue

        if row.item_tax_template != item_tax_templates[row.item_code]:
            items_with_duplicate_taxes.append(bold(row.item_code))

    if items_with_duplicate_taxes:
        frappe.throw(
            _(
                "Cannot use different Item Tax Templates in different rows for"
                " following items:<br> {0}"
            ).format("<br>".join(items_with_duplicate_taxes)),
            title="Inconsistent Item Tax Templates",
        )


def validate_place_of_supply(doc):
    valid_options = get_place_of_supply_options(
        as_list=True,
    )

    if doc.place_of_supply not in valid_options:
        frappe.throw(
            _(
                '"<strong>{0}</strong>" is not a valid Place of Supply. Please choose'
                " from available options."
            ).format(doc.place_of_supply),
            title=_("Invalid Place of Supply"),
        )

    if (
        doc.doctype in SALES_DOCTYPES
        and doc.gst_category == "Overseas"
        and doc.place_of_supply != "96-Other Countries"
        and (
            not doc.shipping_address_name
            or frappe.db.get_value("Address", doc.shipping_address_name, "country")
            != "India"
        )
    ):
        frappe.throw(
            _(
                "GST Category is set to <strong>Overseas</strong> but Place of Supply"
                " is within India. Shipping Address in India is required for classifing"
                " this as B2C."
            ),
            title=_("Invalid Shipping Address"),
        )


def is_inter_state_supply(doc):
    return doc.gst_category == "SEZ" or (
        doc.place_of_supply[:2] != get_source_state_code(doc)
    )


def get_source_state_code(doc):
    """
    Get the state code of the state from which goods / services are being supplied.
    Logic opposite to that of utils.get_place_of_supply
    """

    if doc.doctype in SALES_DOCTYPES or doc.doctype == "Payment Entry":
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


def validate_hsn_codes(doc):
    validate_hsn_code, valid_hsn_length = get_hsn_settings()

    if not validate_hsn_code:
        return

    return _validate_hsn_codes(doc, valid_hsn_length, message=None)


def _validate_hsn_codes(doc, valid_hsn_length, message=None):
    rows_with_missing_hsn = []
    rows_with_invalid_hsn = []

    for item in doc.items:
        if not (hsn_code := item.get("gst_hsn_code")):
            rows_with_missing_hsn.append(str(item.idx))

        elif len(hsn_code) not in valid_hsn_length:
            rows_with_invalid_hsn.append(str(item.idx))

    if doc.docstatus == 1:
        # Same error for erroneous rows on submit
        rows_with_invalid_hsn += rows_with_missing_hsn

        if not rows_with_invalid_hsn:
            return

        frappe.throw(
            _(
                "{0}"
                "Please enter a valid HSN/SAC code for the following row numbers:"
                " <br>{1}"
            ).format(message or "", frappe.bold(", ".join(rows_with_invalid_hsn))),
            title=_("Invalid HSN/SAC"),
        )

    if rows_with_missing_hsn:
        frappe.msgprint(
            _(
                "{0}" "Please enter HSN/SAC code for the following row numbers: <br>{1}"
            ).format(message or "", frappe.bold(", ".join(rows_with_missing_hsn))),
            title=_("Invalid HSN/SAC"),
        )

    if rows_with_invalid_hsn:
        frappe.msgprint(
            _(
                "{0}"
                "HSN/SAC code should be {1} digits long for the following"
                " row numbers: <br>{2}"
            ).format(
                message or "",
                join_list_with_custom_separators(valid_hsn_length),
                frappe.bold(", ".join(rows_with_invalid_hsn)),
            ),
            title=_("Invalid HSN/SAC"),
        )


def validate_overseas_gst_category(doc):
    if not is_overseas_doc(doc):
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


def get_regional_round_off_accounts(company, account_list):
    country = frappe.get_cached_value("Company", company, "country")
    if country != "India" or not frappe.get_cached_value(
        "GST Settings", "GST Settings", "round_off_gst_values"
    ):
        return account_list

    if isinstance(account_list, str):
        account_list = json.loads(account_list)

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

    is_sales_transaction = doctype in SALES_DOCTYPES or doctype == "Payment Entry"
    party_details = frappe.parse_json(party_details)
    gst_details = frappe._dict()

    # Party/Address Defaults
    party_address_field = (
        "customer_address" if is_sales_transaction else "supplier_address"
    )
    if not party_details.get(party_address_field):
        party_gst_details = get_party_gst_details(party_details, is_sales_transaction)

        # updating party details to get correct place of supply
        if party_gst_details:
            party_details.update(party_gst_details)
            gst_details.update(party_gst_details)

    # POS
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

    # set is_reverse_charge as per party_gst_details if not set
    if not is_sales_transaction and "is_reverse_charge" not in party_details:
        is_reverse_charge = frappe.db.get_value(
            "Supplier",
            party_details.supplier,
            "is_reverse_charge_applicable as is_reverse_charge",
            as_dict=True,
        )

        if is_reverse_charge:
            party_details.update(is_reverse_charge)
            gst_details.update(is_reverse_charge)

    if doctype == "Payment Entry":
        return gst_details

    # Taxes Not Applicable
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

    # Tax Category in Transaction
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

    # Fetch template by perceived tax
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
        party_details.is_reverse_charge,
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

    if not (party := party_details.get(party_type.lower())) or not isinstance(
        party, str
    ):
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


def get_tax_template(
    master_doctype, company, is_inter_state, state_code, is_reverse_charge
):
    tax_categories = frappe.get_all(
        "Tax Category",
        fields=["name", "is_inter_state", "gst_state"],
        filters={
            "is_inter_state": 1 if is_inter_state else 0,
            "is_reverse_charge": 1 if is_reverse_charge else 0,
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

    if doc.get("itc_classification") == "All Other ITC":
        doc.itc_classification = "ITC on Reverse Charge"


def is_export_without_payment_of_gst(doc):
    return is_overseas_doc(doc) and not doc.is_export_with_gst


class ItemGSTDetails:
    def get(self, docs, doctype, company):
        """
        Return Item GST Details for a list of documents
        """
        self.set_gst_accounts_and_item_defaults(doctype, company)
        self.set_tax_amount_precisions(doctype)

        response = frappe._dict()

        if not self.gst_account_map:
            return response

        for doc in docs:
            self.doc = doc
            if not doc.get("items") or not doc.get("taxes"):
                continue

            self.set_item_wise_tax_details()

            for item in doc.get("items"):
                response[item.name] = self.get_item_tax_detail(item)

        return response

    def update(self, doc):
        """
        Update Item GST Details for a single document
        """
        self.doc = doc
        if not self.doc.get("items"):
            return

        self.set_gst_accounts_and_item_defaults(doc.doctype, doc.company)
        if not self.gst_account_map:
            return

        self.set_tax_amount_precisions(doc.doctype)
        self.set_item_wise_tax_details()
        self.update_item_tax_details()

    def set_gst_accounts_and_item_defaults(self, doctype, company):
        if doctype in SALES_DOCTYPES:
            account_type = "Output"
        else:
            account_type = "Input"

        gst_account_map = get_gst_accounts_by_type(company, account_type, throw=False)
        self.gst_account_map = {v: k for k, v in gst_account_map.items()}

        item_defaults = frappe._dict(count=0)

        for row in GST_TAX_TYPES:
            item_defaults[f"{row}_rate"] = 0
            item_defaults[f"{row}_amount"] = 0

        self.item_defaults = item_defaults

    def set_item_wise_tax_details(self):
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
            key = row.item_code or row.item_name

            if key not in tax_details:
                tax_details[key] = self.item_defaults.copy()
            tax_details[key]["count"] += 1

        for row in self.doc.taxes:
            if (
                not row.tax_amount
                or not row.item_wise_tax_detail
                or row.account_head not in self.gst_account_map
            ):
                continue

            account_type = self.gst_account_map[row.account_head]
            tax = account_type[:-8]
            tax_rate_field = f"{tax}_rate"
            tax_amount_field = f"{tax}_amount"

            old = json.loads(row.item_wise_tax_detail)

            tax_difference = row.tax_amount

            # update item taxes
            for item_name in old:
                if item_name not in tax_details:
                    # Do not compute if Item is not present in Item table
                    # There can be difference in Item Table and Item Wise Tax Details
                    continue

                item_taxes = tax_details[item_name]
                tax_rate, tax_amount = old[item_name]

                tax_difference -= tax_amount

                # cases when charge type == "Actual"
                if tax_amount and not tax_rate:
                    continue

                item_taxes[tax_rate_field] = tax_rate
                item_taxes[tax_amount_field] += tax_amount

            # Floating point errors
            tax_difference = flt(tax_difference, 5)

            # Handle rounding errors
            if tax_difference:
                item_taxes[tax_amount_field] += tax_difference

        self.item_tax_details = tax_details

    def update_item_tax_details(self):
        for item in self.doc.get("items"):
            item.update(self.get_item_tax_detail(item))

    def get_item_key(self, item):
        return item.item_code or item.item_name

    def get_item_tax_detail(self, item):
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

            tax_amount_field = f"{tax}_amount"
            precision = self.precision.get(tax_amount_field)

            multiplier = (
                item.qty if tax == "cess_non_advol" else item.taxable_value / 100
            )
            tax_amount = flt(tax_rate * multiplier, precision)

            item_tax_detail[tax_amount_field] -= tax_amount

            response.update({tax_amount_field: tax_amount})

        return response

    def set_tax_amount_precisions(self, doctype):
        item_doctype = f"{doctype} Item"
        meta = frappe.get_meta(item_doctype)

        self.precision = frappe._dict()
        default_precision = cint(frappe.db.get_default("float_precision")) or 3

        for tax_type in GST_TAX_TYPES:
            fieldname = f"{tax_type}_amount"
            field = meta.get_field(fieldname)
            if not field:
                continue

            self.precision[fieldname] = field.precision or default_precision


class ItemGSTTreatment:
    def set(self, doc):
        self.doc = doc
        is_sales_transaction = doc.doctype in SALES_DOCTYPES

        if is_sales_transaction and is_overseas_doc(doc):
            self.set_for_overseas()
            return

        self.gst_accounts = get_all_gst_accounts(self.doc.company)
        has_gst_accounts = any(
            row.account_head in self.gst_accounts for row in self.doc.taxes
        )

        if not has_gst_accounts:
            self.set_for_no_taxes()
            return

        self.update_gst_treatment_map()
        self.set_default_treatment()

    def set_for_overseas(self):
        for item in self.doc.items:
            item.gst_treatment = "Zero-Rated"

    def set_for_no_taxes(self):
        for item in self.doc.items:
            if item.gst_treatment not in ("Exempted", "Non-GST"):
                item.gst_treatment = "Nil-Rated"

    def update_gst_treatment_map(self):
        item_templates = set()
        gst_treatments = set()
        gst_treatment_map = {}

        for item in self.doc.items:
            item_templates.add(item.item_tax_template)
            gst_treatments.add(item.gst_treatment)

        if any(
            gst_treatment in gst_treatments
            for gst_treatment in ["Zero-Rated", "Nil-Rated"]
        ):
            # doc changed from overseas to local sale post
            # taxes added after save
            _gst_treatments = frappe.get_all(
                "Item Tax Template",
                filters={"name": ("in", item_templates)},
                fields=["name", "gst_treatment"],
            )
            gst_treatment_map = {row.name: row.gst_treatment for row in _gst_treatments}

        self.gst_treatment_map = gst_treatment_map

    def set_default_treatment(self):
        default_treatment = self.get_default_treatment()

        for item in self.doc.items:
            if item.gst_treatment in ("Zero-Rated", "Nil-Rated"):
                item.gst_treatment = self.gst_treatment_map.get(item.item_tax_template)

            if not item.gst_treatment or not item.item_tax_template:
                item.gst_treatment = default_treatment

    def get_default_treatment(self):
        default = "Taxable"

        for row in self.doc.taxes:
            if row.charge_type in ("Actual", "On Item Quantity"):
                continue

            if row.account_head not in self.gst_accounts:
                continue

            if row.rate == 0:
                default = "Nil-Rated"

            break

        return default


def set_reverse_charge_as_per_gst_settings(doc):
    if doc.doctype in SALES_DOCTYPES:
        return

    gst_settings = frappe.get_cached_value(
        "GST Settings",
        "GST Settings",
        ("enable_rcm_for_unregistered_supplier", "rcm_threshold"),
        as_dict=1,
    )

    if (
        not gst_settings.enable_rcm_for_unregistered_supplier
        or not doc.gst_category == "Unregistered"
        or (doc.grand_total and doc.grand_total <= gst_settings.rcm_threshold)
        or doc.get("is_opening") == "Yes"
    ):
        return

    set_reverse_charge(doc)


def set_reverse_charge(doc):
    doc.is_reverse_charge = 1
    is_inter_state = is_inter_state_supply(doc)

    # get defaults
    default_tax = get_tax_template(
        "Purchase Taxes and Charges Template",
        doc.company,
        is_inter_state,
        doc.company_gstin[:2],
        doc.is_reverse_charge,
    )

    if not default_tax:
        return

    template = (
        get_taxes_and_charges("Purchase Taxes and Charges Template", default_tax) or []
    )

    # compare accounts
    all_gst_accounts, applicable_gst_accounts = get_applicable_gst_accounts(
        doc.company,
        for_sales=False,
        is_inter_state=is_inter_state,
        is_reverse_charge=True,
    )
    existing_accounts = set(
        row.account_head for row in doc.taxes if row.account_head in all_gst_accounts
    )
    has_invalid_accounts = existing_accounts - applicable_gst_accounts

    if has_invalid_accounts:
        return

    has_same_accounts = not (applicable_gst_accounts - existing_accounts)

    # update taxes
    if doc.taxes_and_charges == default_tax and has_same_accounts:
        return

    doc.taxes_and_charges = default_tax
    doc.set("taxes", template)


def validate_gstin_status(gstin, transaction_date):
    settings = frappe.get_cached_doc("GST Settings")
    if not settings.validate_gstin_status:
        return

    gstin_doc = get_gstin_status(gstin, transaction_date)

    if not gstin_doc:
        return

    _validate_gstin_info(gstin_doc, transaction_date, throw=True)


def validate_gst_transporter_id(doc):
    if not doc.get("gst_transporter_id"):
        return

    settings = frappe.get_cached_doc("GST Settings")
    if not settings.validate_gstin_status:
        return

    doc.gst_transporter_id = validate_gstin(
        doc.gst_transporter_id, label="GST Transporter ID", is_transporter_id=True
    )

    gstin_doc = get_gstin_status(doc.gst_transporter_id)

    if not gstin_doc:
        return

    _validate_gst_transporter_id_info(gstin_doc, throw=True)


def validate_company_address_field(doc):
    if doc.doctype not in DOCTYPES_WITH_GST_DETAIL:
        return

    company_address_field = "company_address"
    if doc.doctype not in SALES_DOCTYPES:
        company_address_field = "billing_address"

    if (
        validate_mandatory_fields(
            doc,
            company_address_field,
            _(
                "Please set {0} to ensure Company GSTIN is fetched in the transaction."
            ).format(bold(doc.meta.get_label(company_address_field))),
        )
        is False
    ):
        return False


def before_validate_transaction(doc, method=None):
    if ignore_gst_validations(doc):
        return False

    if not doc.place_of_supply:
        doc.place_of_supply = get_place_of_supply(doc, doc.doctype)

    set_reverse_charge_as_per_gst_settings(doc)


def validate_transaction(doc, method=None):
    if ignore_gst_validations(doc):
        return False

    validate_items(doc)

    if doc.place_of_supply:
        validate_place_of_supply(doc)
    else:
        doc.place_of_supply = get_place_of_supply(doc, doc.doctype)

    if validate_company_address_field(doc) is False:
        return False

    if validate_mandatory_fields(doc, ("company_gstin", "place_of_supply")) is False:
        return False

    # Ignore validation for Quotation not to Customer
    if doc.doctype != "Quotation" or doc.quotation_to == "Customer":
        if (
            validate_mandatory_fields(
                doc,
                "gst_category",
                _(
                    "{0} is a mandatory field for GST Transactions. Please ensure that"
                    " it is set in the Party and / or Address."
                ),
            )
            is False
        ):
            return False

    elif not doc.gst_category:
        doc.gst_category = "Unregistered"

    validate_overseas_gst_category(doc)

    if is_sales_transaction := doc.doctype in SALES_DOCTYPES:
        validate_hsn_codes(doc)
        gstin = doc.billing_address_gstin
    elif doc.doctype == "Payment Entry":
        is_sales_transaction = True
        gstin = doc.billing_address_gstin
    else:
        validate_reverse_charge_transaction(doc)
        gstin = doc.supplier_gstin

    validate_gstin_status(gstin, doc.get("posting_date") or doc.get("transaction_date"))
    validate_gst_transporter_id(doc)
    validate_ecommerce_gstin(doc)

    validate_gst_category(doc.gst_category, gstin)

    valid_accounts = validate_gst_accounts(doc, is_sales_transaction) or ()
    update_taxable_values(doc, valid_accounts)
    validate_item_wise_tax_detail(doc, valid_accounts)


def before_print(doc, method=None, print_settings=None):
    if ignore_gst_validations(doc) or not doc.place_of_supply or not doc.company_gstin:
        return

    set_gst_breakup(doc)


def onload(doc, method=None):
    if ignore_gst_validations(doc) or not doc.place_of_supply or not doc.company_gstin:
        return

    set_gst_breakup(doc)


def validate_ecommerce_gstin(doc):
    if not doc.get("ecommerce_gstin"):
        return

    doc.ecommerce_gstin = validate_gstin(
        doc.ecommerce_gstin, label="E-commerce GSTIN", is_tcs_gstin=True
    )


def update_gst_details(doc, method=None):
    ItemGSTTreatment().set(doc)
    if doc.doctype in DOCTYPES_WITH_GST_DETAIL:
        ItemGSTDetails().update(doc)
        validate_item_tax_template(doc)


def validate_item_tax_template(doc):
    if not doc.items or not doc.taxes:
        return

    non_taxable_items_with_tax = []
    taxable_items_with_no_tax = []

    for item in doc.items:
        if item.gst_treatment == "Zero-Rated" and not doc.get("is_export_with_gst"):
            continue

        total_taxes = abs(item.igst_amount + item.cgst_amount + item.sgst_amount)

        if total_taxes and item.gst_treatment in ("Nil-Rated", "Exempted", "Non-GST"):
            non_taxable_items_with_tax.append(item.idx)

        if not total_taxes and item.gst_treatment in ("Taxable", "Zero-Rated"):
            taxable_items_with_no_tax.append(item.idx)

    # Case: Zero Tax template with taxes or missing GST Accounts
    if non_taxable_items_with_tax:
        frappe.throw(
            _(
                "Cannot charge GST on Non-Taxable Items.<br>"
                "Are the taxes setup correctly in Item Tax Template? Please select"
                " the correct Item Tax Template for following row numbers:<br>{0}"
            ).format(", ".join(bold(row_no) for row_no in non_taxable_items_with_tax)),
            title=_("Invalid Items"),
        )

    # Case: Taxable template with missing GST Accounts
    if taxable_items_with_no_tax:
        frappe.throw(
            _(
                "No GST is being charged on Taxable Items.<br>"
                "Are there missing GST accounts in Item Tax Template? Please"
                " verify the Item Tax Template for following row numbers:<br>{0}"
            ).format(", ".join(bold(row_no) for row_no in taxable_items_with_no_tax)),
            title=_("Invalid Items"),
        )


def after_mapping(target_doc, method=None, source_doc=None):
    # Copy e-Waybill fields only from DN to SI
    if not source_doc or source_doc.doctype not in (
        "Delivery Note",
        "Purchase Receipt",
    ):
        return

    for field in E_WAYBILL_INV_FIELDS:
        fieldname = field.get("fieldname")
        target_doc.set(fieldname, source_doc.get(fieldname))


def ignore_gst_validations(doc):
    if not is_indian_registered_company(doc) or doc.get("is_opening") == "Yes":
        return True


def on_change_item(doc, method=None):
    """
    Objective:
    Child item is saved before trying to update parent doc.
    Hence we can't verify has_value_changed for items in the parent doc.

    Solution:
    - Set a flag in on_change of item
    - Runs for both insert and save (update after submit)
    - Set flag only if `ignore_validate_update_after_submit` is set

    Reference:
    erpnext.controllers.accounts_controller.update_child_qty_rate
    """
    if doc.flags.ignore_validate_update_after_submit:
        frappe.flags.through_update_item = True


def before_update_after_submit(doc, method=None):
    if not frappe.flags.through_update_item:
        return

    if ignore_gst_validations(doc):
        return

    validate_items(doc)

    if is_sales_transaction := doc.doctype in SALES_DOCTYPES:
        validate_hsn_codes(doc)

    valid_accounts = validate_gst_accounts(doc, is_sales_transaction) or ()
    update_taxable_values(doc, valid_accounts)
    validate_item_wise_tax_detail(doc, valid_accounts)
    update_gst_details(doc)
