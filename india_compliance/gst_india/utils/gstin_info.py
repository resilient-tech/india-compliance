import json
from datetime import timedelta
from string import whitespace

import frappe
from frappe import _
from frappe.utils import getdate

from india_compliance.exceptions import GSPServerError
from india_compliance.gst_india.api_classes.base import BASE_URL
from india_compliance.gst_india.api_classes.e_invoice import EInvoiceAPI
from india_compliance.gst_india.api_classes.e_waybill import EWaybillAPI
from india_compliance.gst_india.api_classes.public import PublicAPI
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    process_gstr_1_returns_info,
)
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
def get_gstin_info(gstin, *, throw_error=True):
    if not frappe.get_cached_doc("User", frappe.session.user).has_desk_access():
        frappe.throw(_("Not allowed"), frappe.PermissionError)

    return _get_gstin_info(gstin, throw_error=throw_error)


def _get_gstin_info(gstin, *, throw_error=True):
    validate_gstin(gstin)
    response = get_archived_gstin_info(gstin)

    if not response:
        try:
            if frappe.cache.get_value("gst_server_error"):
                return frappe._dict()

            response = PublicAPI().get_gstin_info(gstin)
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
        response.tradeNam if response.ctb == "Proprietorship" else response.lgnm
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

    completed_requestes = frappe.get_all(
        "Integration Request",
        {
            "status": "Completed",
            "url": ("=", f"{BASE_URL}/{PublicAPI.BASE_PATH}/search"),
            "data": ("like", f"%{gstin}%"),
            "modified": (">", archive_date_limit),
        },
        pluck="output",
        limit=1,
    )

    if not completed_requestes:
        return

    response = json.loads(completed_requestes[0], object_hook=frappe._dict)

    return response.result


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


def fetch_gstin_status(*, gstin=None, throw=True):
    """
    Fetch GSTIN status from E-Invoice API or Public API

    Uses Public API if credentials are not available or its a user initiated request

    :param gstin: GSTIN to fetch status for
    :param throw: Raise exception if error occurs (used for user initiated requests)
    """
    validate_gstin(gstin)

    try:
        if not throw and frappe.cache.get_value("gst_server_error"):
            return

        gst_settings = frappe.get_cached_doc("GST Settings", None)
        company_gstin = gst_settings.get_gstin_with_credentials(service="e-Invoice")

        if throw or not company_gstin:
            response = PublicAPI().get_gstin_info(gstin)
            return get_formatted_response_for_status(response)

        response = EInvoiceAPI(company_gstin=company_gstin).get_gstin_info(gstin)
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


def fetch_transporter_id_status(transporter_id, throw=True):
    """
    Fetch Transporter ID status from E-Waybill API

    :param transporter_id: GSTIN of the transporter
    :param throw: Raise exception if error occurs (used for user initiated requests)
    """
    if not frappe.get_cached_value("GST Settings", None, "enable_e_waybill"):
        return

    gst_settings = frappe.get_cached_doc("GST Settings", None)
    company_gstin = gst_settings.get_gstin_with_credentials(service="e-Waybill")

    if not company_gstin:
        return

    try:
        response = EWaybillAPI(company_gstin=company_gstin).get_transporter_details(
            transporter_id
        )

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
# "United Nation Body"                      0717UNO00157UNO 0717UNO00211UN2 2117UNO00002UNF
# "Consulate or Embassy of Foreign Country" 0717UNO00154UNU
# "Tax Collector (e-Commerce Operator)"     29AABCF8078M1C8 27AAECG3736E1C2 29AAFCB7707D1C1

# ###### CANNOT BE A PART OF GSTR1 ######
# "Non Resident Online Services Provider"   9917SGP29001OST      Google

# "Non Resident Taxable Person"
# "Government Department ID"


####################################################################################################
#### GSTIN RETURNS INFO ##########################################################################
####################################################################################################


def get_gstr_1_return_status(
    company, gstin, period, process_info=True, year_increment=0
):
    """Returns Returns info for the given period"""
    fy = get_fy(period, year_increment=year_increment)

    response = PublicAPI().get_returns_info(gstin, fy)
    if not response:
        return

    if process_info:
        frappe.enqueue(
            process_gstr_1_returns_info,
            company=company,
            gstin=gstin,
            response=response,
            enqueue_after_commit=True,
        )

    for info in response.get("EFiledlist"):
        if info["rtntype"] == "GSTR1" and info["ret_prd"] == period:
            return info["status"]

    # late filing possibility (limitation: only checks for the next FY: good enough)
    if not year_increment and get_current_fy() != fy:
        get_gstr_1_return_status(
            company, gstin, period, process_info=process_info, year_increment=1
        )

    return "Not Filed"


def get_fy(period, year_increment=0):
    month, year = period[:2], period[2:]
    year = str(int(year) + year_increment)

    # For the month of March, it's filed in the next FY
    if int(month) < 3:
        return f"{int(year) - 1}-{year[-2:]}"
    else:
        return f"{year}-{int(year[-2:]) + 1}"


def get_current_fy():
    period = getdate().strftime("%m%Y")
    return get_fy(period)
