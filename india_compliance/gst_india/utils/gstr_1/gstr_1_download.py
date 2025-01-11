import frappe
from frappe import _
from frappe.utils import cint

from india_compliance.gst_india.api_classes.taxpayer_returns import GSTR1API
from india_compliance.gst_india.doctype.gstr_import_log.gstr_import_log import (
    create_import_log,
)
from india_compliance.gst_india.utils.gstr_1 import GovJsonKey
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import (
    convert_to_internal_data_format,
)

ACTIONS = [
    "B2B",
    "B2CL",
    "B2CS",
    "CDNR",
    "CDNUR",
    "EXP",
    "NIL",
    "AT",
    "TXP",
    # "SUPECO", # 403 Forbidden TODO: Check when this is active
    "HSNSUM",
    "DOCISS",
]


def download_gstr1_json_data(gstr1_log):
    """
    Download GSTR-1 and Unfiled GSTR1 data from GST Portal
    """
    gstin = gstr1_log.gstin
    return_period = gstr1_log.return_period

    is_queued = False
    json_data = frappe._dict()
    api = GSTR1API(gstr1_log)

    if gstr1_log.filing_status == "Filed":
        return_type = "GSTR1"
        data_field = "filed"

        summary = api.get_gstr_1_data("RETSUM", return_period)
        actions = get_sections_to_download(summary)
        json_data.update(summary)

    else:
        return_type = "Unfiled GSTR1"
        data_field = "unfiled"
        actions = ACTIONS

    # download data
    for action in actions:
        response = api.get_gstr_1_data(action, return_period)

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

    gstr1_log.db_set("is_nil", json_data.isnil == "Y")

    mapped_data = convert_to_internal_data_format(json_data)
    gstr1_log.update_json_for(data_field, mapped_data, reset_reconcile=True)

    if is_queued:
        gstr1_log.update_status("Queued")

        frappe.publish_realtime(
            "gstr1_queued",
            message={"gstin": gstin, "return_period": return_period},
            user=frappe.session.user,
        )

    return mapped_data, is_queued


def save_gstr_1(gstin, return_period, json_data, return_type):
    if return_type == "GSTR1":
        data_field = "filed"

    elif return_type == "Unfiled GSTR1":
        data_field = "unfiled"

    if not json_data:
        frappe.throw(
            _(
                "Data received seems to be invalid from the GST Portal. Please try"
                " again or raise support ticket."
            ),
            title=_("Invalid Response Received."),
        )

    mapped_data = convert_to_internal_data_format(json_data)

    gstr1_log = frappe.get_doc("GST Return Log", f"GSTR1-{return_period}-{gstin}")
    gstr1_log.update_json_for(data_field, mapped_data, overwrite=False)
    gstr1_log.update_status("Generated")


def save_gstr_1_filed_data(gstin, return_period, json_data):
    save_gstr_1(gstin, return_period, json_data, "GSTR1")


def save_gstr_1_unfiled_data(gstin, return_period, json_data):
    save_gstr_1(gstin, return_period, json_data, "Unfiled GSTR1")


def get_sections_to_download(summary):
    if summary.isnil:
        return []

    SECTION_ACTION_MAP = {
        "B2B": "B2B",
        "B2CL": "B2CL",
        "B2CS": "B2CS",
        "CDNR": "CDNR",
        "CDNUR": "CDNUR",
        "EXP": "EXP",
        "NIL": "NIL",
        "AT": "AT",
        "TXPD": "TXP",
        "HSN": "HSNSUM",
        "DOC_ISSUE": "DOCISS",
    }

    actions = set()

    for row in summary.get(GovJsonKey.RET_SUM.value, []):
        section = row.get("sec_nm")

        # total no of records
        if row.get("ttl_rec") == 0:
            continue

        if section in SECTION_ACTION_MAP:
            actions.add(SECTION_ACTION_MAP[section])

    return list(actions)
