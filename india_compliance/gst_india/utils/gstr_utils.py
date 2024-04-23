from enum import Enum

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from india_compliance.gst_india.api_classes.returns import ReturnsAPI
from india_compliance.gst_india.doctype.gstr_import_log.gstr_import_log import (
    create_import_log,
    toggle_scheduled_jobs,
)
from india_compliance.gst_india.utils import get_gstin_list


class ReturnType(Enum):
    GSTR2A = "GSTR2a"
    GSTR2B = "GSTR2b"


@frappe.whitelist()
def validate_company_gstins(company=None, company_gstin=None):
    """
    Checks the validity of the company's GSTIN authentication.

    Args:
        company_gstin (str): The GSTIN of the company to validate.

    Returns:
        dict: A dictionary where the keys are the GSTINs and the values are booleans indicating whether the authentication is valid.
    """
    frappe.has_permission("GST Settings", throw=True)

    credentials = get_company_gstin_credentials(company, company_gstin)

    if company_gstin and not credentials:
        frappe.throw(
            _("Missing GSTIN credentials for GSTIN: {gstin}.").format(
                gstin=company_gstin
            )
        )

    if not credentials:
        frappe.throw(_("Missing credentials in GST Settings"))

    if company and not company_gstin:
        missing_credentials = set(get_gstin_list(company)) - set(
            credential.gstin for credential in credentials
        )

        if missing_credentials:
            frappe.throw(
                _("Missing GSTIN credentials for GSTIN(s): {gstins}.").format(
                    gstins=", ".join(missing_credentials),
                )
            )

    gstin_authentication_status = {
        credential.gstin: (
            credential.session_expiry
            and credential.auth_token
            and credential.session_expiry > add_to_date(now_datetime(), minutes=30)
        )
        for credential in credentials
    }

    return gstin_authentication_status


def get_company_gstin_credentials(company=None, company_gstin=None):
    filters = {"service": "Returns"}

    if company:
        filters["company"] = company

    if company_gstin:
        filters["gstin"] = company_gstin

    return frappe.get_all(
        "GST Credential",
        filters=filters,
        fields=["gstin", "session_expiry", "auth_token"],
    )


@frappe.whitelist()
def request_otp(company_gstin):
    frappe.has_permission("GST Settings", throw=True)

    return ReturnsAPI(company_gstin).request_otp()


@frappe.whitelist()
def authenticate_otp(company_gstin, otp):
    frappe.has_permission("GST Settings", throw=True)

    api = ReturnsAPI(company_gstin)
    response = api.autheticate_with_otp(otp)

    return api.process_response(response)


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
    from india_compliance.gst_india.utils.gstr_2 import _download_gstr_2a, save_gstr_2b

    GSTR_FUNCTIONS = {
        ReturnType.GSTR2A.value: _download_gstr_2a,
        ReturnType.GSTR2B.value: save_gstr_2b,
    }

    try:
        api = ReturnsAPI(doc.gstin)
        response = api.download_files(
            doc.return_period,
            doc.request_id,
        )

    except Exception as e:
        frappe.db.delete("GSTR Import Log", doc.name)
        raise e

    if response.error_type in ["otp_requested", "invalid_otp"]:
        return toggle_scheduled_jobs(stopped=True)

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
