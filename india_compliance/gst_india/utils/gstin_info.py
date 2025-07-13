import json
from datetime import timedelta
from string import whitespace

from pypika import Order

import frappe
from frappe import _, request_cache
from frappe.query_builder.functions import Concat, Substring
from frappe.utils import add_to_date, cint

from india_compliance.exceptions import GSPServerError
from india_compliance.gst_india.api_classes.base import BASE_URL
from india_compliance.gst_india.api_classes.nic.e_invoice import EInvoiceAPI
from india_compliance.gst_india.api_classes.nic.e_waybill import EWaybillAPI
from india_compliance.gst_india.api_classes.public import PublicAPI
from india_compliance.gst_india.api_classes.taxpayer_base import (
    otp_handler,
)
from india_compliance.gst_india.api_classes.taxpayer_returns import GSTR1API
from india_compliance.gst_india.utils import parse_datetime, titlecase, validate_gstin

GST_CATEGORIES = {
    "Regular": "Registered Regular",
    "Input Service Distributor (ISD)": "Input Service Distributor",
    "Composition": "Registered Composition",
    "Tax Deductor": "Tax Deductor",
    "Tax Collector (Electronic Commerce Operator)": "Tax Collector",
    "SEZ Unit": "SEZ",
    "SEZ Developer": "SEZ",
    "United Nation Body": "UIN Holders",
    "Consulate or Embassy of Foreign Country": "UIN Holders",
    "URP": "Unregistered",
}

# order of address keys is important
KEYS_TO_SANITIZE = ("dst", "stcd", "pncd", "bno", "flno", "bnm", "st", "loc", "city")
KEYS_TO_FILTER_DUPLICATES = frozenset(("dst", "bnm", "st", "loc", "city"))
CHARACTERS_TO_STRIP = f"{whitespace},"


@frappe.whitelist()
def get_gstin_info(gstin, *, doc=None, throw_error=True):
    if doc and isinstance(doc, str):
        doc = frappe.parse_json(doc)

    if not frappe.get_cached_doc("User", frappe.session.user).has_desk_access():
        frappe.throw(_("Not allowed"), frappe.PermissionError)

    return _get_gstin_info(gstin, doc=doc, throw_error=throw_error)


def _get_gstin_info(gstin, *, doc=None, throw_error=True):
    gstin = validate_gstin(gstin)
    response = get_archived_gstin_info(gstin)

    if not response:
        try:
            if frappe.cache.get_value("gst_server_error"):
                return frappe._dict()

            response = PublicAPI(doc).get_gstin_info(gstin)
            frappe.enqueue(
                "india_compliance.gst_india.doctype.gstin.gstin.create_or_update_gstin_status",
                queue="long",
                response=get_formatted_response_for_status(response),
            )

        except Exception as exc:
            if isinstance(exc, GSPServerError):
                frappe.cache.set_value("gst_server_error", True, expires_in_sec=60)

            if throw_error:
                raise exc

            frappe.log_error(title="Failed to Fetch GSTIN Info", message=exc)
            frappe.clear_last_message()
            return frappe._dict()

    business_name = (
        response.tradeNam
        if response.ctb in ["Proprietorship", "Hindu Undivided Family"]
        else response.lgnm
    )

    gstin_info = frappe._dict(
        gstin=response.gstin,
        business_name=titlecase(business_name or ""),
        gst_category=GST_CATEGORIES.get(response.dty, ""),
        status=response.sts,
    )

    if permanent_address := response.get("pradr"):
        # permanent address will be at the first position
        all_addresses = [permanent_address, *response.get("adadr", [])]
        gstin_info.all_addresses = list(map(_get_address, all_addresses))
        gstin_info.permanent_address = gstin_info.all_addresses[0]

    return gstin_info


def get_archived_gstin_info(gstin):
    """
    Use Integration Requests to get the GSTIN info if available
    """
    archive_days = frappe.get_cached_value(
        "GST Settings", None, "archive_party_info_days"
    )

    if not archive_days:
        return

    archive_date_limit = frappe.utils.now_datetime() - timedelta(days=archive_days)

    archived_response = frappe.db.get_value(
        "Integration Request",
        {
            "status": "Completed",
            "url": ("=", f"{BASE_URL}/{PublicAPI.BASE_PATH}/search"),
            "data": ("like", f"%{gstin}%"),
            "modified": (">", archive_date_limit),
        },
        "output",
    )

    if not archived_response:
        return

    try:
        archived_response = json.loads(archived_response, object_hook=frappe._dict)
    except json.JSONDecodeError:
        return

    return archived_response.result


def _get_address(address):
    """:param address: dict of address with a key of 'addr' and 'ntr'"""

    address = address.get("addr", {})
    address_lines = _extract_address_lines(address)
    return {
        "address_line1": address_lines[0],
        "address_line2": address_lines[1],
        "city": titlecase(address.get("dst")),
        "state": titlecase(address.get("stcd")),
        "pincode": address.get("pncd"),
        "country": "India",
    }


def _extract_address_lines(address):
    """merge and divide address into exactly two lines"""
    unique_values = set()

    for key in KEYS_TO_SANITIZE:
        value = address.get(key, "").strip(CHARACTERS_TO_STRIP)

        if key not in KEYS_TO_FILTER_DUPLICATES:
            address[key] = value
            continue

        if value not in unique_values:
            address[key] = value
            unique_values.add(value)
            continue

        address[key] = ""

    address_line1 = ", ".join(
        titlecase(value)
        for key in ("bno", "flno", "bnm")
        if (value := address.get(key))
    )

    address_line2 = ", ".join(
        titlecase(value) for key in ("loc", "city") if (value := address.get(key))
    )

    if not (street := address.get("st")):
        return address_line1, address_line2

    street = titlecase(street)
    if len(address_line1) > len(address_line2):
        address_line2 = f"{street}, {address_line2}"
    else:
        address_line1 = f"{address_line1}, {street}"

    return address_line1, address_line2


def fetch_gstin_status(*, gstin=None, doc=None, throw=True):
    """
    Fetch GSTIN status from E-Invoice API or Public API

    Uses Public API if credentials are not available or its a user initiated request

    :param gstin: GSTIN to fetch status for
    :param throw: Raise exception if error occurs (used for user initiated requests)
    """
    gstin = validate_gstin(gstin)

    try:
        if not throw and frappe.cache.get_value("gst_server_error"):
            return

        gst_settings = frappe.get_cached_doc("GST Settings", None)
        company_gstin = gst_settings.get_gstin_with_credentials(service="e-Invoice")

        if throw or not company_gstin:
            response = PublicAPI(doc).get_gstin_info(gstin)
            return get_formatted_response_for_status(response)

        doc = doc or frappe._dict()
        doc.company_gstin = company_gstin
        response = EInvoiceAPI.create(doc=doc).get_gstin_info(gstin)
        return frappe._dict(
            {
                "gstin": gstin,
                "registration_date": parse_datetime(response.DtReg, throw=False),
                "cancelled_date": parse_datetime(response.DtDReg, throw=False),
                "status": response.Status,
                "is_blocked": response.BlkStatus,
            }
        )

    except Exception as e:
        if throw:
            raise e

        if isinstance(e, GSPServerError):
            frappe.cache.set_value("gst_server_error", True, expires_in_sec=60)

        frappe.log_error(
            title=_("Error fetching GSTIN status"),
            message=frappe.get_traceback(),
        )
        frappe.clear_last_message()


def get_formatted_response_for_status(response):
    """
    Format response from Public API
    """
    return frappe._dict(
        {
            "gstin": response.gstin,
            "registration_date": parse_datetime(
                response.rgdt, day_first=True, throw=False
            ),
            "cancelled_date": parse_datetime(
                response.cxdt, day_first=True, throw=False
            ),
            "status": response.sts,
        }
    )


def fetch_transporter_id_status(transporter_id, doc=None, throw=True):
    """
    Fetch Transporter ID status from E-Waybill API

    :param transporter_id: GSTIN of the transporter
    :param throw: Raise exception if error occurs (used for user initiated requests)
    """
    if not frappe.get_cached_value("GST Settings", None, "enable_e_waybill"):
        return

    gst_settings = frappe.get_cached_doc("GST Settings", None)
    doc = doc or frappe._dict()
    doc.company_gstin = gst_settings.get_gstin_with_credentials(service="e-Waybill")

    if not doc.company_gstin:
        return

    try:
        # fetched using first credentials
        response = EWaybillAPI.create(doc=doc).get_transporter_details(transporter_id)

    except Exception as e:
        if throw:
            raise e

        frappe.log_error(
            title=_("Error fetching Transporter ID status"),
            message=frappe.get_traceback(),
        )
        frappe.clear_last_message()
        return

    return frappe._dict(
        {
            "gstin": transporter_id,
            "transporter_id_status": "Active" if response.transin else "Invalid",
        }
    )


# ####### SAMPLE DATA for GST_CATEGORIES ########
# "Composition"                             36AASFP8573D2ZN
# "Input Service Distributor (ISD)"         29AABCF8078M2ZW     Flipkart
# "Tax Deductor"                            06DELI09652G1DA 09ALDN00287A1DD 27AAFT56212B1DO 19AAACI1681G1DV
# "SEZ Developer"                           27AAJCS5738D1Z6
# "United Nation Body"                      0717UNO00157UNO 0717UNO00211UN2 2117UNO00002UNF 3317USA00002UNE
# "Consulate or Embassy of Foreign Country" 0717UNO00154UNU
# "Tax Collector (e-Commerce Operator)"     29AABCF8078M1C8 27AAECG3736E1C2 29AAFCB7707D1C1

# ###### CANNOT BE A PART OF GSTR1 ######
# "Non Resident Online Services Provider"   9917SGP29001OST      Google

# "Non Resident Taxable Person"
# "Government Department ID"


####################################################################################################
#### GSTIN RETURNS INFO ##########################################################################
####################################################################################################


def get_gstr_1_return_status(company, gstin, period, year_increment=0):
    """Returns Returns-info for the given period"""
    fy = get_fy(period, year_increment=year_increment)
    e_filed_list = update_gstr_returns_info(company, gstin, fy)

    for info in e_filed_list:
        if info["rtntype"] == "GSTR1" and info["ret_prd"] == period:
            return info["status"]

    # late filing possibility (limitation: only checks for the next FY: good enough)
    if not year_increment and get_previous_period_fy() != fy:
        get_gstr_1_return_status(company, gstin, period, year_increment=1)

    return "Not Filed"


def update_gstr_returns_info(company, gstin, fy=None):
    if frappe.flags.in_test:
        return

    if not fy:
        fy = get_previous_period_fy()

    response = PublicAPI().get_returns_info(gstin, fy)
    if not response:
        return

    e_filed_list = response.get("EFiledlist") or []

    from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
        process_gstr_returns_info,
    )

    # If api call is made then update logs for GSTR1 AND GSTR3B
    frappe.enqueue(
        process_gstr_returns_info,
        company=company,
        gstin=gstin,
        e_filed_list=e_filed_list,
        enqueue_after_commit=True,
    )

    return e_filed_list


def get_latest_3b_filed_period(company, company_gstin):
    log = frappe.qb.DocType("GST Return Log")

    return (
        frappe.qb.from_(log)
        .select(log.return_period)
        .where(log.company == company)
        .where(log.gstin == company_gstin)
        .where(log.return_type == "GSTR3B")
        .where(log.filing_status == "Filed")
        .orderby(
            # eg: 202411
            Concat(
                Substring(log.return_period, 3, 4),  # year
                Substring(log.return_period, 1, 2),  # month
            ),
            order=Order.desc,
        )
        .limit(1)
        .run(pluck=True)
    )


####################################################################################################
#### GSTIN FILING PREFERENCE ######################################################################
####################################################################################################


@frappe.whitelist()
@otp_handler
def get_and_update_filing_preference(gstin, period):
    frappe.has_permission("GST Return Log", throw=True)

    response = fetch_filing_preference(gstin, get_fy(period))

    # update GST Return Log
    create_or_update_logs_for_year(gstin, period, response)

    return get_filing_preference(period, response)


@request_cache
def fetch_filing_preference(gstin, fy):
    api = GSTR1API(company_gstin=gstin)
    response = api.fetch_filing_preference(fy=fy)

    return response


def create_or_update_logs_for_year(gstin, period, response):
    log_names = get_logs_for_year(gstin, period)
    existing_log = frappe._dict(
        frappe.get_all(
            "GST Return Log",
            filters={"name": ["in", log_names]},
            fields=["name", "filing_preference"],
            as_list=True,
        )
    )

    for log_name in log_names:
        period = log_name.split("-")[1]
        filing_preference = get_filing_preference(period, response)

        if not filing_preference:
            continue

        if log_name in existing_log:
            if existing_log[log_name] == filing_preference:
                continue

            # books may need a refresh
            frappe.db.set_value(
                "GST Return Log",
                log_name,
                {"filing_preference": filing_preference, "is_latest_data": 0},
            )
            continue

        frappe.get_doc(
            {
                "doctype": "GST Return Log",
                "name": log_name,
                "return_type": log_name.split("-")[0],
                "filing_preference": filing_preference,
                "return_period": log_name.split("-")[1],
                "gstin": gstin,
            }
        ).insert()

    # patch
    from india_compliance.patches.v15.update_return_logs_with_filing_preference import (
        patch_filing_preference,
    )

    patch_filing_preference(gstin)


def get_filing_preference(period, response):
    quarter = get_financial_quarter(cint(period[:2]))
    for data in response:
        if data.get("quarter") == f"Q{quarter}":
            return "Quarterly" if data.get("preference") == "Q" else "Monthly"

    return None


####################################################################################################
#### GSTIN UTILITIES ###############################################################################
####################################################################################################


def get_fy(period, year_increment=0):
    month, year = period[:2], period[2:]
    year = str(int(year) + year_increment)

    # For the month of March, it's filed in the next FY
    if int(month) < 3:
        return f"{int(year) - 1}-{year[-2:]}"
    else:
        return f"{year}-{int(year[-2:]) + 1}"


def get_previous_period_fy():
    # Best possible scenario is that the return was filed in the previous period.
    period = add_to_date(None, months=-1).strftime("%m%Y")
    return get_fy(period)


def get_logs_for_year(gstin, period):
    year = cint(period[2:])
    month = cint(period[:2])
    logs = []

    if month <= 3:
        year -= 1

    for return_type in ["GSTR1", "GSTR3B"]:
        for current_month in range(1, 13):
            current_year = year if current_month >= 4 else year + 1
            logs.append(f"{return_type}-{current_month:02d}{current_year}-{gstin}")

    return logs


def get_financial_quarter(month):
    if month in [4, 5, 6]:
        return 1  # April, May, June
    elif month in [7, 8, 9]:
        return 2  # July, August, September
    elif month in [10, 11, 12]:
        return 3  # October, November, December
    elif month in [1, 2, 3]:
        return 4  # January, February, March
    else:
        raise ValueError("Month must be between 1 and 12")
