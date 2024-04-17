import frappe
from frappe import _
from frappe.utils import cint

from india_compliance.gst_india.api_classes.returns import GSTR1API
from india_compliance.gst_india.doctype.gstr_import_log.gstr_import_log import (
    create_import_log,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import (
    convert_to_internal_data_format,
)

"""
Download GSTR-1 and e-Invoices data from GST Portal
"""


GSTR1_ACTIONS = [
    "B2B",
    "B2BA",
    "AT",
    "ATA",
    "B2CL",
    "B2CLA",
    "B2CS",
    "B2CSA",
    "CDNR",
    "CDNRA",
    "CDNUR",
    "CDNURA",
    "DOCISS",
    "EXP",
    "EXPA",
    "HSNSUM",
    "NIL",
    "TXP",
    "TXPA",
]

E_INVOICE_ACTIONS = ["B2B", "CDNR", "CDNUR", "EXP"]


def download_gstr1_json_data(gstr1_log):
    gstin = gstr1_log.gstin
    return_period = gstr1_log.return_period

    is_queued = False
    json_data = frappe._dict()
    api = GSTR1API(gstin)

    if gstr1_log.filing_status == "Filed":
        return_type = "GSTR1"
        actions = GSTR1_ACTIONS
        api_method = api.get_gstr_1_data
        data_field = "filed_gstr1"

    else:
        return_type = "e-Invoice"
        actions = E_INVOICE_ACTIONS
        api_method = api.get_einvoice_data
        data_field = "e_invoice_data"

    # download data
    for action in actions:
        response = api_method(action, return_period)

        if response.error_type in ["otp_requested", "invalid_otp"]:
            # TODO: Send message to UI (listener), update log status to OTP Requested
            return response, None

        if response.error_type == "no_docs_found":
            continue

        # Queued
        if response.token:
            create_import_log(
                gstin,
                return_type,
                return_period,
                classification=action,
                request_id=response.token,
                retry_after_mins=cint(response.est),
            )
            is_queued = True
            continue

        if response.error_type:
            continue

        json_data.update(response)

    mapped_data = convert_to_internal_data_format(json_data)
    gstr1_log.update_json_for(data_field, mapped_data)

    if is_queued:
        # TODO: Send message to UI (listener), update log status to queued & restrict report generation
        gstr1_log.update_status("Queued")

        frappe.publish_realtime(
            "gstr1_queued",
            message={"gstin": gstin, "return_period": return_period},
            user=frappe.session.user,
            doctype="GSTR-1 Beta",
        )

    return mapped_data, is_queued


def save_gstr_1(gstin, return_period, json_data, return_type):
    if return_type == "GSTR1":
        data_field = "filed_gstr1"

    elif return_type == "e-Invoice":
        data_field = "e_invoice_data"

    if not json_data:
        frappe.throw(
            _(
                "Data received seems to be invalid from the GST Portal. Please try"
                " again or raise support ticket."
            ),
            title=_("Invalid Response Received."),
        )

    mapped_data = convert_to_internal_data_format(json_data)

    gstr1_log = frappe.get_doc("GSTR-1 Filed Log", f"{return_period}-{gstin}")
    gstr1_log.update_json_for(data_field, mapped_data, overwrite=False)


def save_gstr_1_filed_data(gstin, return_period, json_data):
    save_gstr_1(gstin, return_period, json_data, "GSTR1")


def save_einvoice_data(gstin, return_period, json_data):
    save_gstr_1(gstin, return_period, json_data, "e-Invoice")
