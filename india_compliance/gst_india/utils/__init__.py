from dateutil import parser
from pytz import timezone
from titlecase import titlecase as _titlecase

import frappe
from frappe import _
from frappe.desk.form.load import get_docinfo, run_onload
from frappe.utils import cint, cstr, get_datetime, get_link_to_form, get_system_timezone

from india_compliance.gst_india.constants import (
    ABBREVIATIONS,
    COUNTRY_CODES,
    E_INVOICE_MASTER_CODES_URL,
    GST_ACCOUNT_FIELDS,
    GSTIN_FORMATS,
    PAN_NUMBER,
    PINCODE_FORMAT,
    SALES_DOCTYPES,
    STATE_NUMBERS,
    STATE_PINCODE_MAPPING,
    TCS,
    TIMEZONE,
    UOM_MAP,
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


def validate_gstin(
    gstin,
    label="GSTIN",
    *,
    is_tcs_gstin=False,
    is_transporter_id=False,
):
    """
    Validate GSTIN with following checks:
    - Length should be 15
    - Validate GSTIN Check Digit (except for Unique Common Enrolment Number for Transporters)
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

    if not (is_transporter_id and gstin.startswith("88")):
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


def validate_pincode(address):
    """
    Validate Pincode with following checks:
    - Pincode should be a 6-digit number and cannot start with 0.
    - First 3 digits of Pincode should match with State Mapping as per e-Invoice Master Codes.

    @param address: Address document to validate
    """
    if address.country != "India" or not address.pincode:
        return

    if not PINCODE_FORMAT.match(address.pincode):
        frappe.throw(
            _(
                "Postal Code for Address {0} must be a 6-digit number and cannot start"
                " with 0"
            ).format(get_link_to_form("Address", address.name)),
            title=_("Invalid Postal Code"),
        )

    if address.state not in STATE_PINCODE_MAPPING:
        return

    first_three_digits = cint(address.pincode[:3])
    pincode_range = STATE_PINCODE_MAPPING[address.state]

    if type(pincode_range[0]) == int:
        pincode_range = (pincode_range,)

    for lower_limit, upper_limit in pincode_range:
        if lower_limit <= int(first_three_digits) <= upper_limit:
            return

    frappe.throw(
        _(
            "Postal Code {postal_code} for address {name} is not associated with {state}. Ensure the initial three digits"
            " of your postal code align correctly with the state as per the <a href='{url}'>e-Invoice Master Codes</a>."
        ).format(
            postal_code=frappe.bold(address.pincode),
            name=(
                get_link_to_form("Address", address.name)
                if not address.get("__unsaved")
                else ""
            ),
            state=frappe.bold(address.state),
            url=E_INVOICE_MASTER_CODES_URL,
        ),
        title=_("Invalid Postal Code"),
    )


def guess_gst_category(gstin: str | None, country: str | None) -> str:
    if not gstin:
        if country and country != "India":
            return "Overseas"

        return "Unregistered"

    if GSTIN_FORMATS["Tax Deductor"].match(gstin):
        return "Tax Deductor"

    if GSTIN_FORMATS["Registered Regular"].match(gstin):
        return "Registered Regular"

    if GSTIN_FORMATS["UIN Holders"].match(gstin):
        return "UIN Holders"

    if GSTIN_FORMATS["Overseas"].match(gstin):
        return "Overseas"


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


def is_overseas_doc(doc):
    return is_overseas_transaction(doc.doctype, doc.gst_category, doc.place_of_supply)


def is_overseas_transaction(doctype, gst_category, place_of_supply):
    if gst_category == "SEZ":
        return True

    if doctype in SALES_DOCTYPES:
        return is_foreign_transaction(gst_category, place_of_supply)

    return gst_category == "Overseas"


def is_foreign_doc(doc):
    return is_foreign_transaction(doc.gst_category, doc.place_of_supply)


def is_foreign_transaction(gst_category, place_of_supply):
    return gst_category == "Overseas" and place_of_supply == "96-Other Countries"


def get_hsn_settings():
    validate_hsn_code, min_hsn_digits = frappe.get_cached_value(
        "GST Settings",
        "GST Settings",
        ("validate_hsn_code", "min_hsn_digits"),
    )

    valid_hsn_length = (4, 6, 8) if cint(min_hsn_digits) == 4 else (6, 8)

    return validate_hsn_code, valid_hsn_length


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


@frappe.whitelist()
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


def join_list_with_custom_separators(input, separator=", ", last_separator=" or "):
    if type(input) not in (list, tuple):
        return

    if not input:
        return

    if len(input) == 1:
        return cstr(input[0])

    return (
        separator.join(cstr(item) for item in input[:-1])
        + last_separator
        + cstr(input[-1])
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


def get_gst_uom(uom, settings=None):
    """Returns the GST UOM from ERPNext UOM"""
    settings = settings or frappe.get_cached_doc("GST Settings")

    for row in settings.get("gst_uom_map"):
        if row.uom == uom:
            return row.gst_uom.split("(")[0].strip()

    uom = uom.upper()
    if uom in UOM_MAP:
        return uom

    return next((k for k, v in UOM_MAP.items() if v == uom), "OTH")


def get_place_of_supply_options(*, as_list=False, with_other_countries=False):
    options = []

    for state_name, state_number in STATE_NUMBERS.items():
        options.append(f"{state_number}-{state_name}")

    if with_other_countries:
        options.append("96-Other Countries")

    if as_list:
        return options

    return "\n".join(sorted(options))


def are_goods_supplied(doc):
    return any(
        item
        for item in doc.items
        if item.gst_hsn_code
        and not item.gst_hsn_code.startswith("99")
        and item.qty != 0
    )


def get_validated_country_code(country):
    if country == "India":
        return

    code = frappe.db.get_value("Country", country, "code")

    if not code:
        frappe.throw(
            _(
                "Country Code not found for {0}. Please set it as per the <a href='{1}'>e-Invoice Master Codes</a>"
            ).format(
                frappe.bold(get_link_to_form("Country", country)),
                E_INVOICE_MASTER_CODES_URL,
            )
        )

    code = code.upper()

    if code not in COUNTRY_CODES:
        frappe.throw(
            _(
                "Country Code for {0} ({1}) does not match with the <a href='{2}'>e-Invoice Master Codes</a>"
            ).format(
                frappe.bold(get_link_to_form("Country", country, country)),
                frappe.bold(code),
                E_INVOICE_MASTER_CODES_URL,
            )
        )

    return code
