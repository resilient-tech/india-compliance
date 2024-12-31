from enum import Enum

import frappe
from frappe import _
from frappe.query_builder.terms import Criterion
from frappe.utils import cint

from india_compliance.gst_india.api_classes.taxpayer_returns import (
    IMSAPI,
    GSTR2aAPI,
    GSTR2bAPI,
)
from india_compliance.gst_india.constants import IMS_CLASSIFICATION_MAP
from india_compliance.gst_india.doctype.gst_invoice_management_system import (
    get_inward_supplies_to_upload,
    update_return_log,
)
from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    verify_request_in_progress,
)
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    create_ims_return_log,
)
from india_compliance.gst_india.doctype.gstr_import_log.gstr_import_log import (
    create_import_log,
)
from india_compliance.gst_india.utils import get_party_for_gstin
from india_compliance.gst_india.utils.gstr_2 import gstr_2a, gstr_2b, ims
from india_compliance.gst_india.utils.gstr_utils import ReturnType


class GSTRCategory(Enum):
    B2B = "B2B"
    B2BA = "B2BA"
    CDNR = "CDNR"
    CDNRA = "CDNRA"
    ISD = "ISD"
    ISDA = "ISDA"  # for GSTR 2B only
    IMPG = "IMPG"
    IMPGSEZ = "IMPGSEZ"

    # IMS
    B2BCN = "B2BCN"
    B2BCNA = "B2BCNA"
    B2BDN = "B2BDN"
    B2BDNA = "B2BDNA"


GSTR_2A_ACTIONS = {
    "B2B": GSTRCategory.B2B,
    "B2BA": GSTRCategory.B2BA,
    "CDN": GSTRCategory.CDNR,
    "CDNA": GSTRCategory.CDNRA,
    "ISD": GSTRCategory.ISD,
    "IMPG": GSTRCategory.IMPG,
    "IMPGSEZ": GSTRCategory.IMPGSEZ,
}

IMS_ACTIONS = {
    "B2B": GSTRCategory.B2B,
    "B2BA": GSTRCategory.B2BA,
    "CN": GSTRCategory.B2BCN,
    "CNA": GSTRCategory.B2BCNA,
    "DN": GSTRCategory.B2BDN,
    "DNA": GSTRCategory.B2BDNA,
}


GSTR_MODULES = {
    ReturnType.GSTR2A.value: gstr_2a,
    ReturnType.GSTR2B.value: gstr_2b,
    ReturnType.IMS.value: ims,
}

IMPORT_CATEGORY = ("IMPG", "IMPGSEZ")


def download_gstr_2a(gstin, return_periods, gst_categories=None):
    total_expected_requests = len(return_periods) * len(GSTR_2A_ACTIONS)
    requests_made = 0
    queued_message = False

    return_type = ReturnType.GSTR2A
    api = GSTR2aAPI(gstin)
    for return_period in return_periods:
        is_last_period = return_periods[-1] == return_period

        json_data = frappe._dict({"gstin": gstin, "fp": return_period})
        has_data = False
        for action, category in GSTR_2A_ACTIONS.items():
            requests_made += 1

            frappe.publish_realtime(
                "update_api_progress",
                {
                    "current_progress": requests_made * 100 / total_expected_requests,
                    "return_period": return_period,
                    "is_last_period": is_last_period,
                },
                user=frappe.session.user,
                doctype="Purchase Reconciliation Tool",
            )

            if gst_categories and category.value not in gst_categories:
                continue

            response = api.get_data(action, return_period)

            if response.error_type == "no_docs_found":
                create_import_log(
                    gstin,
                    return_type.value,
                    return_period,
                    classification=category.value,
                    data_not_found=True,
                )
                continue

            # Queued
            if response.token:
                create_import_log(
                    gstin,
                    return_type.value,
                    return_period,
                    classification=category.value,
                    request_id=response.token,
                    retry_after_mins=cint(response.est),
                )
                queued_message = True
                continue

            if response.error_type:
                continue

            if not (data := response.get(action.lower())):
                frappe.throw(
                    _(
                        "Data received seems to be invalid from the GST Portal. Please try"
                        " again or raise support ticket."
                    ),
                    title=_("Invalid Response Received."),
                )

            # making consistent with GSTR2a upload
            json_data[action.lower()] = data
            has_data = True

        save_gstr_2a(gstin, return_period, json_data)

    if queued_message:
        show_queued_message()

    if not has_data:
        end_transaction_progress(return_period)


def download_gstr_2b(gstin, return_periods):
    total_expected_requests = len(return_periods)
    requests_made = 0
    queued_message = False

    api = GSTR2bAPI(gstin)
    for return_period in return_periods:
        has_data = False
        is_last_period = return_periods[-1] == return_period
        requests_made += 1
        frappe.publish_realtime(
            "update_api_progress",
            {
                "current_progress": requests_made * 100 / total_expected_requests,
                "return_period": return_period,
                "is_last_period": is_last_period,
            },
            user=frappe.session.user,
            doctype="Purchase Reconciliation Tool",
        )

        response = api.get_data(return_period)

        if response.error_type == "not_generated":
            frappe.msgprint(
                _("No record is found in GSTR-2B or generation is still in progress"),
                title=_("Not Generated"),
            )
            continue

        if response.error_type == "no_docs_found":
            create_import_log(
                gstin, ReturnType.GSTR2B.value, return_period, data_not_found=True
            )
            continue

        if response.error_type == "queued":
            create_import_log(
                gstin,
                ReturnType.GSTR2B.value,
                return_period,
                request_id=response.requestid,
                retry_after_mins=response.retryTimeInMinutes,
            )
            queued_message = True
            continue

        if response.error_type:
            continue

        has_data = True

        # Handle multiple files for GSTR2B
        if response.data and (file_count := response.data.get("fc")):
            for file_num in range(1, file_count + 1):
                r = api.get_data(return_period, file_num=file_num)
                save_gstr_2b(gstin, return_period, r)

            continue  # skip first response if file_count is greater than 1

        save_gstr_2b(gstin, return_period, response)

    if queued_message:
        show_queued_message()

    if not has_data:
        end_transaction_progress(return_period)


def download_ims_invoices(gstin):
    api = IMSAPI(gstin)
    has_queued_invoices = False
    has_non_queued_invoices = False
    # TODO: JSON data preparation for one period

    for action, category in IMS_ACTIONS.items():
        response = api.get_data(action)
        category = category.value

        if response.error_type == "no_docs_found":
            continue

        # Queued
        if response.token:
            create_import_log(
                gstin,
                "IMS",
                "ALL",
                classification=IMS_CLASSIFICATION_MAP[category][0],
                # TODO: classification as data field and used directly
                request_id=response.token,
                retry_after_mins=cint(response.est),
            )
            has_queued_invoices = True
            continue

        has_non_queued_invoices = True
        save_ims_invoices(gstin, None, response)

    create_ims_return_log(gstin)

    if has_queued_invoices:
        frappe.publish_realtime(
            "ims_download_queued",
            message={
                "message": _(
                    "Some categories are queued for download at GSTN as there may be large data."
                    " We will retry download every few minutes until it succeeds."
                )
            },
            user=frappe.session.user,
        )

    if has_non_queued_invoices:
        frappe.publish_realtime(
            "ims_download_completed",
            message={"message": _("Downloaded Invoices successfully")},
            user=frappe.session.user,
        )

    return has_queued_invoices


def save_gstr_2a(gstin, return_period, json_data):
    return_type = ReturnType.GSTR2A
    if (
        not json_data
        or json_data.get("gstin") != gstin
        or json_data.get("fp") != return_period
    ):
        frappe.throw(
            _(
                "Data received seems to be invalid from the GST Portal. Please try"
                " again or raise support ticket."
            ),
            title=_("Invalid Response Received."),
        )

    for action, category in GSTR_2A_ACTIONS.items():
        if action.lower() not in json_data:
            continue

        create_import_log(
            gstin, return_type.value, return_period, classification=category.value
        )

        # making consistent with GSTR2b
        json_data[category.value.lower()] = json_data.pop(action.lower())

    save_gstr(gstin, return_type, return_period, json_data)


def save_gstr_2b(gstin, return_period, json_data):
    json_data = json_data.data
    return_type = ReturnType.GSTR2B
    if not json_data or json_data.get("gstin") != gstin:
        frappe.throw(
            _(
                "Data received seems to be invalid from the GST Portal. Please try"
                " again or raise support ticket."
            ),
            title=_("Invalid Response Received."),
        )

    create_import_log(gstin, return_type.value, return_period)
    save_gstr(
        gstin,
        return_type,
        return_period,
        json_data.get("docdata"),
        json_data.get("gendt"),
    )
    update_import_history(return_period)


def save_ims_invoices(gstin, return_period, json_data):
    save_gstr(gstin, ReturnType.IMS, return_period, json_data)


def save_gstr(
    gstin, return_type: ReturnType, return_period, json_data, gen_date_2b=None
):
    """Save GSTR data to Inward Supply

    :param return_period: str
    :param json_data: dict of list (GSTR category: suppliers)
    :param gen_date_2b: str (Date when GSTR 2B was generated)
    """

    company = get_party_for_gstin(gstin, "Company")
    for category in GSTRCategory:
        gstr = get_data_handler(return_type.value, category.value)
        if not gstr:
            continue

        gstr(company, gstin, return_period, json_data, gen_date_2b).create_transactions(
            category,
            json_data.get(category.value.lower()),
        )


def get_data_handler(return_type, category):
    class_name = return_type + category
    return getattr(GSTR_MODULES[return_type], class_name, None)


def update_import_history(return_periods):
    """Updates 2A data availability from 2B Import"""

    if not (
        inward_supplies := frappe.get_all(
            "GST Inward Supply",
            filters={"return_period_2b": ("in", return_periods)},
            fields=("sup_return_period as return_period", "classification"),
            distinct=True,
        )
    ):
        return

    log = frappe.qb.DocType("GSTR Import Log")
    (
        frappe.qb.update(log)
        .set(log.data_not_found, 0)
        .where(log.data_not_found == 1)
        .where(
            Criterion.any(
                (log.return_period == doc.return_period)
                & (log.classification == doc.classification)
                for doc in inward_supplies
            )
        )
        .run()
    )


def _download_gstr_2a(gstin, return_period, json_data):
    json_data.gstin = gstin
    json_data.fp = return_period
    save_gstr_2a(gstin, return_period, json_data)


def show_queued_message():
    frappe.msgprint(
        _(
            "Some returns are queued for download at GSTN as there may be large data."
            " We will retry download every few minutes until it succeeds.<br><br>"
            "You can track download status from download dialog."
        )
    )


def end_transaction_progress(return_period):
    """
    For last period, set progress to 100% if no data is found
    This will update the progress bar to 100% in the frontend
    """

    frappe.publish_realtime(
        "update_transactions_progress",
        {
            "current_progress": 100,
            "return_period": return_period,
            "is_last_period": True,
        },
        user=frappe.session.user,
        doctype="Purchase Reconciliation Tool",
    )


###################################################################################################################
### IMS Upload ####################################################################################################
###################################################################################################################


def upload_ims_invoices(company_gstin):
    if not frappe.db.exists("GST Return Log", f"IMS-ALL-{company_gstin}"):
        frappe.throw(_("Please download invoices before uploading"))
        return

    ims_log = frappe.get_doc(
        "GST Return Log",
        f"IMS-ALL-{company_gstin}",
    )

    upload_data, reset_data = get_data_for_upload(company_gstin)

    if not (upload_data or reset_data):
        return False

    verify_request_in_progress(ims_log, False)

    api = IMSAPI(company_gstin)

    if upload_data:
        # Upload invoices where action in ["Accepted", "Rejected", "Pending"]
        response = api.save_ims_action(upload_data)
        update_return_log(
            ims_log, response.get("reference_id"), "upload", api.request_id
        )

    if reset_data:
        # Reset invoices where action is "No Action"
        response = api.reset_ims_action(reset_data)
        update_return_log(
            ims_log, response.get("reference_id"), "reset", api.request_id
        )

    return True


def download_and_upload_ims_invoices(company_gstin):
    """
    1. This function will download invoices from GST Portal,
       and if there are some queued invoices then upload will be skipped.

    2. If there are no queued invoices, then it will upload the invoices to GST Portal.

    3. It will check the status regardless of whether any data was uploaded or not.(To notify user that process is completed successfully).
    """

    has_queued_invoices = download_ims_invoices(company_gstin)

    # TODO: flag for pending upload and cron job for queued invoices
    if has_queued_invoices:
        return

    upload_ims_invoices(company_gstin)

    frappe.publish_realtime(
        "check_ims_upload_status",
        user=frappe.session.user,
    )


def get_data_for_upload(company_gstin):
    category_key_map = {
        "Invoice_0": GSTRCategory.B2B.value,
        "Invoice_1": GSTRCategory.B2BA.value,
        "Debit Note_0": GSTRCategory.B2BDN.value,
        "Debit Note_1": GSTRCategory.B2BDNA.value,
        "Credit Note_0": GSTRCategory.B2BCN.value,
        "Credit Note_1": GSTRCategory.B2BCNA.value,
    }

    upload_data = {}
    reset_data = {}
    key_invoice_map = {}

    gst_inward_supply_list = get_inward_supplies_to_upload(company_gstin)

    for invoice in gst_inward_supply_list:
        key = f"{invoice.doc_type}_{invoice.is_amended}"
        key_invoice_map.setdefault(key, []).append(invoice)

    for key, invoices in key_invoice_map.items():
        category = category_key_map[key]
        _class = get_data_handler(ReturnType.IMS.value, category)
        upload_invoices = []
        reset_invoices = []

        for invoice in invoices:
            data = {
                **_class.convert_data_to_gov_format(invoice),
                **_class.get_category_details(invoice),
            }

            if invoice.ims_action != "No Action":
                upload_invoices.append(data)
            else:
                reset_invoices.append(data)

        if upload_invoices:
            upload_data[category.lower()] = upload_invoices

        if reset_invoices:
            reset_data[category.lower()] = reset_invoices

    return upload_data, reset_data
