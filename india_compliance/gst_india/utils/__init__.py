from thefuzz import process

import frappe
from frappe import _
from frappe.utils import cstr
from erpnext.controllers.taxes_and_totals import (
    get_itemised_tax,
    get_itemised_taxable_amount,
)

from india_compliance.gst_india.constants import (
    GSTIN_FORMAT,
    PAN_NUMBER,
    STATE_NUMBERS,
    TCS,
)


def validate_gstin(gstin, gst_category):
    """
    Validate GSTIN with following checks:
    - Length should be 15.
    - GST Category for parties without GSTIN should be Unregistered or Overseas.
    - Validate GSTIN Check Digit.
    - GSTIN of e-Commerce Operator (TCS) is not allowed.
    - GSTIN should match with the regex pattern as per GST Category of the party.
    """
    gstin = gstin.upper().strip()
    if not gstin:
        if gst_category and gst_category not in (
            valid_category := {"Unregistered", "Overseas"}
        ):
            frappe.throw(
                _("GST Category should be one of {0}.").format(
                    ", ".join(valid_category)
                ),
                title=_("Invalid GST Category"),
            )
        return

    if not gst_category:
        frappe.throw(_("Please select GST Category."), title=_("Invalid GST Category"))

    if len(gstin) != 15:
        frappe.throw(_("GSTIN must have 15 characters."), title=_("Invalid GSTIN"))

    validate_gstin_check_digit(gstin)

    if TCS.match(gstin):
        frappe.throw(
            _("GSTIN of e-Commerce Operator (TCS) cannot be used as Party GSTIN."),
            title=_("Invalid GSTIN"),
        )

    valid_gstin_format = GSTIN_FORMAT.get(gst_category)
    if not valid_gstin_format.match(gstin):
        frappe.throw(
            _(
                "GSTIN you have entered doesn't match for category {0}. Please make sure you have entered correct GSTIN and GST Category."
            ).format(gst_category),
            title=_("Invalid GSTIN or GST Category"),
        )


def validate_and_update_pan(doc):
    """
    If PAN is not set, set it from GSTIN.
    If PAN is set, validate it with GSTIN and PAN Format.
    """
    gstin = doc.get("gstin", default="")
    pan = doc.pan = (doc.get("pan") or "").upper().strip()

    if gstin:
        if PAN_NUMBER.match(pan_from_gstin := gstin[2:12]):
            doc.pan = pan_from_gstin

    elif pan:
        validate_pan(pan, gstin)


def validate_pan(pan, gstin):

    pan_match = PAN_NUMBER.match(pan)
    if not pan_match:
        frappe.throw(
            _("Invalid PAN. Please check the PAN and GSTIN."), title=_("Invalid PAN")
        )

    if (
        gstin
        and (pan_from_gstin := gstin[2:12]) != pan
        and PAN_NUMBER.match(pan_from_gstin)
    ):
        frappe.throw(
            _("There is mismatch in PAN and GSTIN. Please check the PAN and GSTIN."),
            title=_("Invalid PAN"),
        )


def read_data_file(file_name):
    file_path = frappe.get_app_path("india_compliance", "gst_india", "data", file_name)
    with open(file_path, "r") as f:
        return f.read()


def set_gst_state_and_state_number(doc):
    """
    Set to State of Address if matched with one from GST State List
    If Not, Find fuzzy match from GST State List and ask user to update state accordingly.
    """
    states_lowercase = {s.lower(): s for s in STATE_NUMBERS}
    state = doc.state.lower().strip()

    if state not in states_lowercase:
        state_match = process.extractOne(state, states_lowercase.keys())
        possible_match = states_lowercase[state_match[0]]
        frappe.throw(
            _(
                "Did you mean {0}? Please update the state to appropriate Indian State."
            ).format(frappe.bold(possible_match)),
            title=_("Invalid State"),
        )
    else:
        doc.state = doc.gst_state = states_lowercase[state]
    doc.gst_state_number = STATE_NUMBERS[doc.gst_state]


def validate_gstin_check_digit(gstin, label="GSTIN"):
    """
    Function to validate the check digit of the GSTIN.
    """
    factor = 1
    total = 0
    code_point_chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    mod = len(code_point_chars)
    input_chars = gstin[:-1]
    for char in input_chars:
        digit = factor * code_point_chars.find(char)
        digit = (digit // mod) + (digit % mod)
        total += digit
        factor = 2 if factor == 1 else 1
    if gstin[-1] != code_point_chars[((mod - (total % mod)) % mod)]:
        frappe.throw(
            _(
                """Invalid {0}! The check digit validation has failed. Please ensure you've typed the {0} correctly."""
            ).format(label)
        )


def get_itemised_tax_breakup_data(doc, account_wise=False, hsn_wise=False):
    itemised_tax = get_itemised_tax(doc.taxes, with_tax_account=account_wise)

    itemised_taxable_amount = get_itemised_taxable_amount(doc.items)

    if not frappe.get_meta(doc.doctype + " Item").has_field("gst_hsn_code"):
        return itemised_tax, itemised_taxable_amount

    hsn_wise_in_gst_settings = frappe.db.get_single_value(
        "GST Settings", "hsn_wise_tax_breakup"
    )

    tax_breakup_hsn_wise = hsn_wise or hsn_wise_in_gst_settings
    if tax_breakup_hsn_wise:
        item_hsn_map = frappe._dict()
        for d in doc.items:
            item_hsn_map.setdefault(d.item_code or d.item_name, d.get("gst_hsn_code"))

    hsn_tax = {}
    for item, taxes in itemised_tax.items():
        item_or_hsn = item if not tax_breakup_hsn_wise else item_hsn_map.get(item)
        hsn_tax.setdefault(item_or_hsn, frappe._dict())
        for tax_desc, tax_detail in taxes.items():
            key = tax_desc
            if account_wise:
                key = tax_detail.get("tax_account")
            hsn_tax[item_or_hsn].setdefault(key, {"tax_rate": 0, "tax_amount": 0})
            hsn_tax[item_or_hsn][key]["tax_rate"] = tax_detail.get("tax_rate")
            hsn_tax[item_or_hsn][key]["tax_amount"] += tax_detail.get("tax_amount")

    # set taxable amount
    hsn_taxable_amount = frappe._dict()
    for item in itemised_taxable_amount:
        item_or_hsn = item if not tax_breakup_hsn_wise else item_hsn_map.get(item)
        hsn_taxable_amount.setdefault(item_or_hsn, 0)
        hsn_taxable_amount[item_or_hsn] += itemised_taxable_amount.get(item)

    return hsn_tax, hsn_taxable_amount


def get_place_of_supply(doc, doctype):
    if not frappe.get_meta("Address").has_field("gst_state"):
        return

    if doctype in ("Sales Invoice", "Delivery Note", "Sales Order"):
        address_name = doc.customer_address or doc.company_address
    elif doctype in ("Purchase Invoice", "Purchase Order", "Purchase Receipt"):
        address_name = doc.shipping_address or doc.supplier_address

    if address_name:
        address = frappe.db.get_value(
            "Address",
            address_name,
            ["gst_state", "gst_state_number", "gstin"],
            as_dict=1,
        )
        if address and address.gst_state and address.gst_state_number:
            doc.gstin = address.gstin
            return cstr(address.gst_state_number) + "-" + cstr(address.gst_state)


@frappe.whitelist()
def get_gstins_for_company(company):
    company_gstins = []
    if company:
        company_gstins = frappe.db.sql(
            """select
			distinct `tabAddress`.gstin
		from
			`tabAddress`, `tabDynamic Link`
		where
			`tabDynamic Link`.parent = `tabAddress`.name and
			`tabDynamic Link`.parenttype = 'Address' and
			`tabDynamic Link`.link_doctype = 'Company' and
			`tabDynamic Link`.link_name = %(company)s""",
            {"company": company},
        )
    return company_gstins


@frappe.whitelist()
def get_gst_accounts(
    company=None, account_wise=False, only_reverse_charge=0, only_non_reverse_charge=0
):
    filters = {"parent": "GST Settings"}

    if company:
        filters.update({"company": company})
    if only_reverse_charge:
        filters.update({"account_type": "Reverse Charge"})
    elif only_non_reverse_charge:
        filters.update({"account_type": ("in", ("Input", "Output"))})

    gst_accounts = frappe._dict()
    gst_settings_accounts = frappe.get_all(
        "GST Account",
        filters=filters,
        fields=["cgst_account", "sgst_account", "igst_account", "cess_account"],
    )

    if (
        not gst_settings_accounts
        and not frappe.flags.in_test
        and not frappe.flags.in_migrate
    ):
        frappe.throw(_("Please set GST Accounts in GST Settings"))

    for d in gst_settings_accounts:
        for acc, val in d.items():
            if not account_wise:
                gst_accounts.setdefault(acc, []).append(val)
            elif val:
                gst_accounts[val] = acc

    return gst_accounts
