import frappe
from frappe import _
from frappe.utils import cstr
from erpnext.controllers.taxes_and_totals import (
    get_itemised_tax,
    get_itemised_taxable_amount,
)

from india_compliance.gst_india.constants import (
    GSTIN_FORMATS,
    PAN_NUMBER,
    STATE_NUMBERS,
    TCS,
)


def validate_gstin(gstin, label="GSTIN", is_tcs_gstin=False):
    """
    Validate GSTIN with following checks:
    - Length should be 15.
    - Validate GSTIN Check Digit.
    - Validate GSTIN of e-Commerce Operator (TCS) (Based on is_tcs_gstin parameter).
    """

    if not gstin:
        return

    gstin = gstin.upper().strip()

    if len(gstin) != 15:
        frappe.throw(
            _("{0} must have 15 characters").format(label),
            title=_("Invalid {0}").format(label),
        )

    validate_gstin_check_digit(gstin, label)

    if is_tcs_gstin and not TCS.match(gstin):
        frappe.throw(
            _("Invalid format for e-Commerce Operator (TCS) GSTIN"),
            title=_("Invalid GSTIN"),
        )

    return gstin


def validate_gst_category(gst_category, gstin):
    """
    Validate GST Category with following checks:
    - GST Category for parties without GSTIN should be Unregistered or Overseas.
    - GSTIN should match with the regex pattern as per GST Category of the party.
    """

    if not gstin:
        if gst_category not in (
            categories_without_gstin := {"Unregistered", "Overseas"}
        ):
            frappe.throw(
                _("GST Category should be one of {0}").format(
                    " or ".join(
                        frappe.bold(category) for category in categories_without_gstin
                    )
                ),
                title=_("Invalid GST Category"),
            )

        return

    if gst_category == "Unregistered":
        frappe.throw(
            "GST Category cannot be Unregistered for party with GSTIN",
        )

    valid_gstin_format = GSTIN_FORMATS.get(gst_category)
    if not valid_gstin_format.match(gstin):
        frappe.throw(
            _(
                "The GSTIN you've entered doesn't match the format for GST Category"
                " {0}. Please ensure you've entered the correct GSTIN and GST Category."
            ).format(frappe.bold(gst_category)),
            title=_("Invalid GSTIN or GST Category"),
        )


def is_valid_pan(pan):
    return PAN_NUMBER.match(pan)


def read_data_file(file_name):
    file_path = frappe.get_app_path("india_compliance", "gst_india", "data", file_name)
    with open(file_path, "r") as f:
        return f.read()


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


def get_place_of_supply(party_details, doctype=None):
    """
    :param party_details: A frappe._dict or document containing fields related to party
    """

    if not doctype:
        # Expect document object
        doctype = party_details.doctype

    if not frappe.get_meta("Address").has_field("gst_state"):
        return

    if doctype in ("Sales Invoice", "Delivery Note", "Sales Order"):
        address_name = party_details.customer_address or party_details.company_address
    elif doctype in ("Purchase Invoice", "Purchase Order", "Purchase Receipt"):
        address_name = party_details.shipping_address or party_details.supplier_address

    if address_name:
        address = frappe.db.get_value(
            "Address",
            address_name,
            ["gst_state", "gst_state_number", "gstin"],
            as_dict=1,
        )

        if address and address.gst_state and address.gst_state_number:
            # TODO: bad idea to set value in getter
            party_details.gstin = address.gstin

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
