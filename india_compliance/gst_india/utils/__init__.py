import copy
import io
import tarfile

from dateutil import parser
from pytz import timezone
from titlecase import titlecase as _titlecase

import frappe
from frappe import _
from frappe.contacts.doctype.contact.contact import get_contact_details
from frappe.desk.form.load import get_docinfo, run_onload
from frappe.utils import (
    add_to_date,
    cint,
    cstr,
    get_datetime,
    get_link_to_form,
    get_system_timezone,
    getdate,
)
from frappe.utils.data import get_timespan_date_range as _get_timespan_date_range
from frappe.utils.file_manager import get_file_path
from erpnext.accounts.party import get_default_contact
from erpnext.accounts.utils import get_fiscal_year

from india_compliance.exceptions import GatewayTimeoutError, GSPServerError
from india_compliance.gst_india.constants import (
    ABBREVIATIONS,
    E_INVOICE_MASTER_CODES_URL,
    GST_ACCOUNT_FIELDS,
    GST_INVOICE_NUMBER_FORMAT,
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
    """

    frappe.has_permission(party_type, doc=party, throw=True)

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


@frappe.whitelist()
def get_party_for_gstin(gstin, party_type="Supplier"):
    if not gstin:
        return

    if party := frappe.db.get_value(
        party_type, filters={"gstin": gstin}, fieldname="name"
    ):
        return party

    address = frappe.qb.DocType("Address")
    links = frappe.qb.DocType("Dynamic Link")
    party = (
        frappe.qb.from_(address)
        .join(links)
        .on(links.parent == address.name)
        .select(links.link_name)
        .where(links.link_doctype == party_type)
        .where(address.gstin == gstin)
        .limit(1)
        .run()
    )
    if party:
        return party[0][0]


@frappe.whitelist()
def get_party_contact_details(party, party_type="Supplier"):
    if party and (contact := get_default_contact(party_type, party)):
        return get_contact_details(contact)


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
            _(
                "GST Category cannot be Unregistered for party with GSTIN",
            )
        )

    if TCS.match(gstin):
        frappe.throw(
            _(
                "e-Commerce Operator (TCS) GSTIN is not allowed for transaction / party / address"
            ),
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

    if isinstance(pincode_range[0], int):
        pincode_range = (pincode_range,)

    for lower_limit, upper_limit in pincode_range:
        if lower_limit <= int(first_three_digits) <= upper_limit:
            return

    frappe.throw(
        _(
            "Postal Code {postal_code} for address {name} is not associated with"
            " {state}. Ensure the initial three digits of your postal code align"
            " correctly with the state as per the <a href='{url}'>e-Invoice Master"
            " Codes</a>."
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


def guess_gst_category(
    gstin: str | None, country: str | None, gst_category: str | None = None
) -> str:
    if not gstin:
        if country and country != "India":
            return "Overseas"

        if not country and gst_category == "Overseas":
            return "Overseas"

        return "Unregistered"

    if GSTIN_FORMATS["Tax Deductor"].match(gstin):
        return "Tax Deductor"

    if GSTIN_FORMATS["Registered Regular"].match(gstin):
        if gst_category in (
            "Registered Regular",
            "Registered Composition",
            "SEZ",
            "Deemed Export",
        ):
            return gst_category

        return "Registered Regular"

    if GSTIN_FORMATS["UIN Holders"].match(gstin):
        return "UIN Holders"

    if GSTIN_FORMATS["Overseas"].match(gstin):
        return "Overseas"

    # eg: e-Commerce Operator (TCS)
    return "Registered Regular"


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

    if doctype in SALES_DOCTYPES or doctype == "Payment Entry":
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

    if doctype in SALES_DOCTYPES or doctype == "Payment Entry":
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
            if gst_state_number and gst_state:
                return f"{gst_state_number}-{gst_state}"

        party_gstin = party_details.billing_address_gstin or party_details.company_gstin
    else:
        party_gstin = party_details.company_gstin or party_details.supplier_gstin

    if not party_gstin:
        return

    state_code = party_gstin[:2]

    if state := get_state(state_code):
        return f"{state_code}-{state}"


def get_escaped_gst_accounts(company, account_type, throw=True):
    gst_accounts = get_gst_accounts_by_type(company, account_type, throw=throw)

    for tax_type in gst_accounts:
        gst_accounts[tax_type] = get_escaped_name(gst_accounts[tax_type])

    return gst_accounts


def get_escaped_name(name):
    """
    This function will replace % in account name with %% to escape it for PyPika
    """
    if not name:
        return

    if "%" not in name:
        return name

    return name.replace("%", "%%")


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


def get_gst_accounts_by_tax_type(company, tax_type, throw=True):
    """
    :param company: Company to get GST Accounts for
    :param tax_type: Tax Type to get GST Accounts for eg: "cgst"

    Returns a list of accounts:
    """
    if not company:
        frappe.throw(_("Please set Company first"))

    tax_type = tax_type.lower()
    field = f"{tax_type}_account"

    if field not in GST_ACCOUNT_FIELDS:
        frappe.throw(_("Invalid Tax Type"))

    settings = frappe.get_cached_doc("GST Settings", "GST Settings")
    accounts_list = []

    has_account_settings = False
    for row in settings.gst_accounts:
        if row.company != company:
            continue

        has_account_settings = True
        if gst_account := row.get(field):
            accounts_list.append(gst_account)

    if accounts_list:
        return accounts_list

    if has_account_settings or not throw:
        return accounts_list

    frappe.throw(
        _(
            "Could not retrieve GST Accounts of type {0} from GST Settings for"
            " Company {1}"
        ).format(frappe.bold(tax_type), frappe.bold(company)),
    )


@frappe.whitelist()
def get_all_gst_accounts(company):
    """
    Permission not checked here:
    List of GST account names isn't considered sensitive data
    """
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


def parse_datetime(value, day_first=False, throw=True):
    """Convert IST string to offset-naive system time"""

    if not value:
        return

    try:
        parsed = parser.parse(value, dayfirst=day_first)
    except Exception as e:
        if not throw:
            return

        raise e

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


def get_json_from_file(path):
    return frappe._dict(frappe.get_file_json(get_file_path(path)))


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


def is_autofill_party_info_enabled():
    settings = frappe.get_cached_doc("GST Settings")
    return (
        is_api_enabled(settings)
        and settings.autofill_party_info
        and not settings.sandbox_mode
    )


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


def get_place_of_supply_options(*, as_list=False):
    options = []

    for state_name, state_number in STATE_NUMBERS.items():
        options.append(f"{state_number}-{state_name}")

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
                "Country Code not found for {0}. Please set it as per the <a"
                " href='{1}'>e-Invoice Master Codes</a>"
            ).format(
                frappe.bold(get_link_to_form("Country", country)),
                E_INVOICE_MASTER_CODES_URL,
            )
        )

    code = code.upper()

    if len(code) != 2:
        frappe.throw(
            _(
                "Country Code for {0} ({1}) must be a 2-letter code. Please set it as per"
                " the <a href='{2}'>e-Invoice Master Codes</a>"
            ).format(
                frappe.bold(get_link_to_form("Country", country, country)),
                frappe.bold(code),
                E_INVOICE_MASTER_CODES_URL,
            )
        )

    return code


def get_timespan_date_range(timespan: str, company: str | None = None) -> tuple | None:
    date_range = _get_timespan_date_range(timespan)

    if date_range:
        return date_range

    company = company or frappe.defaults.get_user_default("Company")

    if timespan == "this fiscal year":
        date = getdate()
        fiscal_year = get_fiscal_year(date, company=company)
        return (fiscal_year[1], fiscal_year[2])

    if timespan == "last fiscal year":
        date = add_to_date(getdate(), years=-1)
        fiscal_year = get_fiscal_year(date, company=company)
        return (fiscal_year[1], fiscal_year[2])

    return


def merge_dicts(d1: dict, d2: dict) -> dict:
    """
    Sample Input:
    -------------
    d1 = {
        'key1': 'value1',
        'key2': {'nested': 'value'},
        'key3': ['value1'],
        'key4': 'value4'
    }
    d2 = {
        'key1': 'value2',
        'key2': {'key': 'value3'},
        'key3': ['value2'],
        'key5': 'value5'
    }

    Sample Output:
    --------------
    {
        'key1': 'value2',
        'key2': {'nested': 'value', 'key': 'value3'},
        'key3': ['value1', 'value2'],
        'key4': 'value4',
        'key5': 'value5'
    }
    """
    for key in set(d1.keys()) | set(d2.keys()):
        if key in d2 and key in d1:
            if isinstance(d1[key], dict) and isinstance(d2[key], dict):
                merge_dicts(d1[key], d2[key])

            elif isinstance(d1[key], list) and isinstance(d2[key], list):
                d1[key] = d1[key] + d2[key]

            else:
                d1[key] = copy.deepcopy(d2[key])

        elif key in d2:
            d1[key] = copy.deepcopy(d2[key])

    return d1


def tar_gz_bytes_to_data(tar_gz_bytes: bytes) -> str | None:
    """
    Return first file in tar.gz ending with .json
    """
    with tarfile.open(fileobj=io.BytesIO(tar_gz_bytes), mode="r:gz") as tar_gz_file:
        for filename in tar_gz_file.getnames():
            if not filename.endswith(".json"):
                continue

            file_in_tar = tar_gz_file.extractfile(filename)

            if not file_in_tar:
                continue

            data = file_in_tar.read().decode("utf-8")
            break

    return data


@frappe.whitelist(methods=["POST"])
def disable_item_tax_template_notification():
    frappe.defaults.clear_user_default("needs_item_tax_template_notification")


def validate_invoice_number(doc):
    """Validate GST invoice number requirements."""

    if len(doc.name) > 16:
        frappe.throw(
            _("GST Invoice Number cannot exceed 16 characters"),
            title=_("Invalid GST Invoice Number"),
        )

    if not GST_INVOICE_NUMBER_FORMAT.match(doc.name):
        frappe.throw(
            _(
                "GST Invoice Number should start with an alphanumeric character and can"
                " only contain alphanumeric characters, dash (-) and slash (/)"
            ),
            title=_("Invalid GST Invoice Number"),
        )


def handle_server_errors(settings, doc, document_type, error):
    if not doc.doctype == "Sales Invoice":
        return

    error_message = "Government services are currently slow/down. We apologize for the inconvenience caused."

    error_message_title = {
        GatewayTimeoutError: _("Gateway Timeout Error"),
        GSPServerError: _("GSP/GST Server Down"),
    }

    document_status_field = (
        "einvoice_status" if document_type == "e-Invoice" else "e_waybill_status"
    )

    document_status = "Failed"

    if settings.enable_retry_einv_ewb_generation:
        document_status = "Auto-Retry"
        settings.db_set(
            "is_retry_einv_ewb_generation_pending", 1, update_modified=False
        )
        error_message += (
            " Your {0} generation will be automatically retried every 5 minutes."
        ).format(document_type)
    else:
        error_message += " Please try again after some time."

    doc.db_set({document_status_field: document_status})

    frappe.msgprint(
        msg=_(error_message),
        title=error_message_title.get(type(error)),
        indicator="yellow",
    )
