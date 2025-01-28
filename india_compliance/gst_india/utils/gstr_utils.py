from enum import Enum

import frappe

from india_compliance.gst_india.api_classes.taxpayer_base import (
    TaxpayerBaseAPI,
    otp_handler,
)
from india_compliance.gst_india.api_classes.taxpayer_returns import IMSAPI, ReturnsAPI
from india_compliance.gst_india.doctype.gstr_import_log.gstr_import_log import (
    create_import_log,
    toggle_scheduled_jobs,
)
from india_compliance.gst_india.utils import create_notification
from india_compliance.gst_india.utils.gstr_1.gstr_1_download import (
    save_gstr_1_filed_data,
    save_gstr_1_unfiled_data,
)


class ReturnType(Enum):
    GSTR2A = "GSTR2a"
    GSTR2B = "GSTR2b"
    GSTR1 = "GSTR1"
    UnfiledGSTR1 = "Unfiled GSTR1"
    IMS = "IMS"


@frappe.whitelist()
def request_otp(company_gstin):
    frappe.has_permission("GST Settings", throw=True)

    return TaxpayerBaseAPI(company_gstin).request_otp()


@frappe.whitelist()
@otp_handler
def authenticate_otp(company_gstin, otp):
    frappe.has_permission("GST Settings", throw=True)

    api = TaxpayerBaseAPI(company_gstin)
    response = api.autheticate_with_otp(otp)

    return api.process_response(response)


@frappe.whitelist()
def generate_evc_otp(company_gstin, pan, request_type):
    frappe.has_permission("GSTR-1 Beta", "write", throw=True)
    return TaxpayerBaseAPI(company_gstin).initiate_otp_for_evc(pan, request_type)


def download_queued_request():
    queued_requests = frappe.get_all(
        "GSTR Import Log",
        filters={"request_id": ["is", "set"]},
        fields=[
            "name",
            "gstin",
            "return_type",
            "classification",
            "return_period",
            "request_id",
            "request_time",
        ],
    )

    if not queued_requests:
        return toggle_scheduled_jobs(stopped=True)

    for doc in queued_requests:
        frappe.enqueue(_download_queued_request, queue="long", doc=doc)


def _download_queued_request(doc):
    from india_compliance.gst_india.utils.gstr_2 import (
        _download_gstr_2a,
        save_gstr_2b,
        save_ims_invoices,
    )

    GSTR_FUNCTIONS = {
        ReturnType.GSTR2A.value: _download_gstr_2a,
        ReturnType.GSTR2B.value: save_gstr_2b,
        ReturnType.GSTR1.value: save_gstr_1_filed_data,
        ReturnType.UnfiledGSTR1.value: save_gstr_1_unfiled_data,
        ReturnType.IMS.value: save_ims_invoices,
    }

    API_CLASS = {
        ReturnType.GSTR2A.value: ReturnsAPI,
        ReturnType.GSTR2B.value: ReturnsAPI,
        ReturnType.GSTR1.value: ReturnsAPI,
        ReturnType.UnfiledGSTR1.value: ReturnsAPI,
        ReturnType.IMS.value: IMSAPI,
    }

    try:
        api = API_CLASS[doc.return_type](doc.gstin)
        response = api.download_files(
            doc.return_period,
            doc.request_id,
        )

    except Exception as e:
        frappe.db.delete("GSTR Import Log", doc.name)
        raise e

    if response.error_type == "no_docs_found":
        return create_import_log(
            doc.gstin,
            doc.return_type,
            doc.return_period,
            doc.classification,
            data_not_found=True,
        )

    if response.error_type == "queued":
        return

    if response.error_type:
        return frappe.db.delete("GSTR Import Log", {"name": doc.name})

    frappe.db.set_value("GSTR Import Log", doc.name, "request_id", None)
    GSTR_FUNCTIONS[doc.return_type](doc.gstin, doc.return_period, response)


def publish_action_status_notification(
    return_type, return_period, request_type, status_cd, gstin, request_id=None
):
    status_message_map = {
        "P": f"Success: {return_type} data {request_type} for GSTIN {gstin} and return period {return_period}",
        "PE": f"Partial Success: {return_type} data {request_type} for GSTIN {gstin} and return period {return_period}",
        "ER": f"Error: {return_type} data {request_type} for GSTIN {gstin} and return period {return_period}",
    }

    message_content = {
        "subject": status_message_map.get(status_cd),
        "body": status_message_map.get(status_cd),
    }

    if return_type == "GSTR-1":
        document_type = "GSTR-1 Beta"
    elif return_type == "IMS":
        document_type = "GST Invoice Management System"

    return frappe.enqueue(
        create_notification,
        queue="long",
        message_content=message_content,
        document_type=document_type,
        request_id=request_id,
    )
