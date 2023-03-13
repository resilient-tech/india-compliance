from dateutil import parser
from pytz import timezone
from titlecase import titlecase as _titlecase

import frappe
from frappe import _
from frappe.desk.form.load import get_docinfo, run_onload
from frappe.utils import cstr, get_datetime, get_system_timezone
from erpnext.controllers.taxes_and_totals import (
    get_itemised_tax,
    get_itemised_taxable_amount,
)

from india_compliance.gst_india.constants import (
    ABBREVIATIONS,
    GST_ACCOUNT_FIELDS,
    GSTIN_FORMATS,
    PAN_NUMBER,
    SALES_DOCTYPES,
    STATE_NUMBERS,
    TCS,
    TIMEZONE,
)


def get_state(state_number):
    """Get state from State Number"""

    state_number = str(state_number).zfill(2)

    for state, code in STATE_NUMBERS.items():
        if code == state_number:
            return state


def load_doc(doctype, name, perm="read"):
    """Get doc, check perms and run onload method"""
    doc = frappe.get_doc(doctype, name)
    doc.check_permission(perm)
    run_onload(doc)

    return doc


def update_onload(doc, key, value):
    """Set or update onload key in doc"""

    if not (onload := doc.get("__onload")):
        onload = frappe._dict()
        doc.set("__onload", onload)

    if not onload.get(key):
        onload[key] = value
    else:
        onload[key].update(value)


def send_updated_doc(doc, set_docinfo=False):
    """Apply fieldlevel perms and send doc if called while handling a request"""

    if not frappe.request:
        return

    doc.apply_fieldlevel_read_permissions()

    if set_docinfo:
        get_docinfo(doc)

    frappe.response.docs.append(doc)


@frappe.whitelist()
def get_gstin_list(party, party_type="Company"):
    """
    Returns a list the party's GSTINs.
    This function doesn't check for permissions since GSTINs are publicly available.
    """

    gstin_list = frappe.get_all(
        "Address",
        filters={
            "link_doctype": party_type,
            "link_name": party,
            "gstin": ("is", "set"),
        },
        pluck="gstin",
        distinct=True,
    )

    default_gstin = frappe.db.get_value(party_type, party, "gstin")
    if default_gstin and default_gstin not in gstin_list:
        gstin_list.insert(0, default_gstin)

    return gstin_list


def validate_gstin(gstin, label="GSTIN", is_tcs_gstin=False):
    """
    Validate GSTIN with following checks:
    - Length should be 15
    - Validate GSTIN Check Digit
    - Validate GSTIN of e-Commerce Operator (TCS) (Based on is_tcs_gstin)
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


def get_data_file_path(file_name):
    return frappe.get_app_path("india_compliance", "gst_india", "data", file_name)


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


def get_place_of_supply(party_details, doctype):
    """
    :param party_details: A frappe._dict or document containing fields related to party
    """

    # fallback to company GSTIN for sales or supplier GSTIN for purchases
    # (in retail scenarios, customer / company GSTIN may not be set)

    if doctype in SALES_DOCTYPES:
        # for exports, Place of Supply is set using GST category in absence of GSTIN
        if party_details.gst_category == "Overseas":
            return "96-Other Countries"

        if (
            party_details.gst_category == "Unregistered"
            and party_details.customer_address
        ):
            gst_state_number, gst_state = frappe.db.get_value(
                "Address",
                party_details.customer_address,
                ("gst_state_number", "gst_state"),
            )
            return f"{gst_state_number}-{gst_state}"

        party_gstin = party_details.billing_address_gstin or party_details.company_gstin
    else:
        party_gstin = party_details.company_gstin or party_details.supplier_gstin

    if not party_gstin:
        return

    state_code = party_gstin[:2]

    if state := get_state(state_code):
        return f"{state_code}-{state}"


def get_gst_accounts_by_type(company, account_type, throw=True):
    """
    :param company: Company to get GST Accounts for
    :param account_type: Account Type to get GST Accounts for

    Returns a dict of accounts:
    {
        "cgst_account": "ABC",
        ...
    }
    """
    if not company:
        frappe.throw(_("Please set Company first"))

    settings = frappe.get_cached_doc("GST Settings", "GST Settings")
    for row in settings.gst_accounts:
        if row.account_type == account_type and row.company == company:
            return frappe._dict((key, row.get(key)) for key in GST_ACCOUNT_FIELDS)

    if not throw:
        return frappe._dict()

    frappe.throw(
        _(
            "Could not retrieve GST Accounts of type {0} from GST Settings for"
            " Company {1}"
        ).format(frappe.bold(account_type), frappe.bold(company)),
        frappe.DoesNotExistError,
    )


def get_all_gst_accounts(company):
    if not company:
        frappe.throw(_("Please set Company first"))

    settings = frappe.get_cached_doc("GST Settings")

    accounts_list = []
    for row in settings.gst_accounts:
        if row.company != company:
            continue

        for account in GST_ACCOUNT_FIELDS:
            if gst_account := row.get(account):
                accounts_list.append(gst_account)

    return accounts_list


def parse_datetime(value, day_first=False):
    """Convert IST string to offset-naive system time"""

    if not value:
        return

    parsed = parser.parse(value, dayfirst=day_first)
    system_tz = get_system_timezone()

    if system_tz == TIMEZONE:
        return parsed.replace(tzinfo=None)

    # localize to india, convert to system, remove tzinfo
    return (
        timezone(TIMEZONE)
        .localize(parsed)
        .astimezone(timezone(system_tz))
        .replace(tzinfo=None)
    )


def as_ist(value=None):
    """Convert system time to offset-naive IST time"""

    parsed = get_datetime(value)
    system_tz = get_system_timezone()

    if system_tz == TIMEZONE:
        return parsed

    # localize to system, convert to IST, remove tzinfo
    return (
        timezone(system_tz)
        .localize(parsed)
        .astimezone(timezone(TIMEZONE))
        .replace(tzinfo=None)
    )


def titlecase(value):
    return _titlecase(value, callback=get_titlecase_version)


def get_titlecase_version(word, all_caps=False, **kwargs):
    """Returns abbreviation if found, else None"""

    if not all_caps:
        word = word.upper()

    elif word.endswith("IDC"):
        # GIDC, MIDC, etc.
        # case maintained if word is already in all caps
        return word

    if word in ABBREVIATIONS:
        return word


def is_api_enabled(settings=None):
    if not settings:
        settings = frappe.get_cached_value(
            "GST Settings",
            "GST Settings",
            ("enable_api", "api_secret"),
            as_dict=True,
        )

    return settings.enable_api and can_enable_api(settings)


def can_enable_api(settings):
    return settings.api_secret or frappe.conf.ic_api_secret
