import frappe
from frappe import _
from frappe.utils import cint

from india_compliance.gst_india.api_classes.public import PublicAPI
from india_compliance.gst_india.api_classes.returns import GSTR1API
from india_compliance.gst_india.doctype.gstr_1_filed_log.gstr_1_filed_log import (
    create_gstr1_filed_log,
    get_gstr1_data,
)
from india_compliance.gst_india.doctype.gstr_import_log.gstr_import_log import (
    create_import_log,
)

GSTR1_ACTIONS = {
    "B2B": "B2B",
    "B2BA": "B2BA",
    "AT": "AT",
    "ATA": "ATA",
    "B2CL": "B2CL",
    "B2CLA": "B2CLA",
    "B2CS": "B2CS",
    "B2CSA": "B2CSA",
    "CDNR": "CDNR",
    "CDNRA": "CDNRA",
    "CDNUR": "CDNUR",
    "CDNURA": "CDNURA",
    "DOCISS": "DOC_ISSUE",
    "EXP": "EXP",
    "EXPA": "EXPA",
    "RETSUM": "SEC_SUM",
    "HSNSUM": "HSN",
    "NIL": "NIL",
    "TXP": "TXP",
    "TXPA": "TXPA",
}

E_INVOICE_ACTIONS = {"B2B": "B2B", "CDNR": "CDNR", "CDNUR": "CDNUR", "EXP": "EXP"}


@frappe.whitelist()
def download_filed_gstr1(gstin, return_periods, otp=None):
    api = GSTR1API(gstin)
    returns_info = get_returns_info(gstin, return_periods)

    queued_message = False
    return_type = "GSTR1"
    for return_period in return_periods:
        json_data = frappe._dict({"gstin": gstin, "fp": return_period})

        for action, category in GSTR1_ACTIONS.items():
            response = api.get_gstr_1_data(action, return_period, otp)

            if response.error_type in ["otp_requested", "invalid_otp"]:
                return response

            if response.error_type == "no_docs_found":
                json_data[action.lower()] = []
                continue

            # Queued
            if response.token:
                create_import_log(
                    gstin,
                    return_type,
                    return_period,
                    classification=category,
                    request_id=response.token,
                    retry_after_mins=cint(response.est),
                )
                queued_message = True
                continue

            if response.error_type:
                continue

            json_data[action.lower()] = response.get(category.lower())

        create_gstr1_filed_log(
            gstin,
            return_period,
            "filed_gstr1",
            json_data,
            returns_info[return_period],
        )

    if queued_message:
        from india_compliance.gst_india.utils.gstr_2 import show_queued_message

        show_queued_message()


@frappe.whitelist()
def download_e_invoices(gstin, return_periods, otp=None):
    api = GSTR1API(gstin)

    queued_message = False
    return_type = "e-Invoice"
    for return_period in return_periods:
        json_data = frappe._dict({"gstin": gstin, "fp": return_period})

        for action, category in E_INVOICE_ACTIONS.items():
            response = api.get_einvoice_data(action, return_period, otp)

            if response.error_type in ["otp_requested", "invalid_otp"]:
                return response

            if response.error_type == "no_docs_found":
                json_data[action.lower()] = []
                continue

            # Queued
            if response.token:
                create_import_log(
                    gstin,
                    return_type,
                    return_period,
                    classification=category,
                    request_id=response.token,
                    retry_after_mins=cint(response.est),
                )
                queued_message = True
                continue

            if response.error_type:
                continue

            json_data[action.lower()] = response.get(category.lower())

        create_gstr1_filed_log(gstin, return_period, "e_invoices", json_data)

    if queued_message:
        from india_compliance.gst_india.utils.gstr_2 import show_queued_message

        show_queued_message()


def get_fy_from_periods(periods):
    fy = set()

    for period in periods:
        month, year = period[:2], period[2:]

        if int(month) < 4:
            fy.add(f"{int(year) - 1}-{year[-2:]}")
        else:
            fy.add(f"{year}-{int(year[-2:]) + 1}")

    return fy


def get_returns_info(gstin, periods):
    "Returns Returns info for the given periods"
    fys = get_fy_from_periods(periods)
    returns_info = []

    for fy in fys:
        response = PublicAPI().get_returns_info(gstin, fy)
        returns_info.extend(response.get("EFiledlist"))

    returns_info_periods = dict.fromkeys(periods)

    for info in returns_info:
        if info["rtntype"] == "GSTR1" and info["ret_prd"] in periods:
            returns_info_periods[info["ret_prd"]] = info

    return returns_info_periods


def save_gstr_1(gstin, return_period, log_type, json_data):
    if not json_data:
        frappe.throw(
            _(
                "Data received seems to be invalid from the GST Portal. Please try"
                " again or raise support ticket."
            ),
            title=_("Invalid Response Received."),
        )

    saved_data = get_gstr1_data(gstin, return_period, log_type)

    for action, category in GSTR1_ACTIONS.items():
        if category.lower() not in json_data:
            continue

        saved_data[action.lower()] = json_data[category.lower()]

    create_gstr1_filed_log(gstin, return_period, log_type, saved_data)


def save_gstr_1_filed_data(gstin, return_period, json_data):
    save_gstr_1(gstin, return_period, "filed_gstr1", json_data)


def save_einvoice_data(gstin, return_period, json_data):
    save_gstr_1(gstin, return_period, "e_invoices", json_data)
