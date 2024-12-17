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
from india_compliance.gst_india.constants import CLASSIFICATION_MAP
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


ACTIONS = {
    "B2B": GSTRCategory.B2B,
    "B2BA": GSTRCategory.B2BA,
    "CDN": GSTRCategory.CDNR,
    "CDNA": GSTRCategory.CDNRA,
    "ISD": GSTRCategory.ISD,
    "IMPG": GSTRCategory.IMPG,
    "IMPGSEZ": GSTRCategory.IMPGSEZ,
}

IMS_CATEGORIES = {
    "b2b": "B2B",
    "b2ba": "B2BA",
    "b2bcn": "CN",
    "b2bcna": "CNA",
    "b2bdn": "DN",
    "b2bdna": "DNA",
}


GSTR_MODULES = {
    ReturnType.GSTR2A.value: gstr_2a,
    ReturnType.GSTR2B.value: gstr_2b,
}

IMPORT_CATEGORY = ("IMPG", "IMPGSEZ")


def download_gstr_2a(gstin, return_periods, gst_categories=None):
    total_expected_requests = len(return_periods) * len(ACTIONS)
    requests_made = 0
    queued_message = False

    return_type = ReturnType.GSTR2A
    api = GSTR2aAPI(gstin)
    for return_period in return_periods:
        is_last_period = return_periods[-1] == return_period

        json_data = frappe._dict({"gstin": gstin, "fp": return_period})
        has_data = False
        for action, category in ACTIONS.items():
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

    for action, category in ACTIONS.items():
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
        gstr = get_data_handler(return_type.value, category)
        gstr(company, gstin, return_period, json_data, gen_date_2b).create_transactions(
            category,
            json_data.get(category.value.lower()),
        )


def get_data_handler(return_type, category):
    class_name = return_type + category.value
    return getattr(GSTR_MODULES[return_type], class_name)


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


def download_ims_invoices(company_gstin, company):
    reset_previous_ims_action()
    api = IMSAPI(company_gstin)
    has_queued_invoices = False
    has_non_queued_invoices = False

    for category in IMS_CATEGORIES:
        response = api.get_data(IMS_CATEGORIES[category])

        if response.error_type == "no_docs_found":
            create_import_log(
                company_gstin,
                "IMS",
                "ALL",
                classification=CLASSIFICATION_MAP[category],
                data_not_found=True,
            )
            continue

        # Queued
        if response.token:
            create_import_log(
                company_gstin,
                "IMS",
                "ALL",
                classification=CLASSIFICATION_MAP[category],
                request_id=response.token,
                retry_after_mins=cint(response.est),
            )
            has_queued_invoices = True
            continue

        has_non_queued_invoices = True
        getattr(ims, category.upper())(company_gstin, company).create_transactions(
            response.get(category, [])
        )

    create_ims_return_log(company, company_gstin)

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
        from india_compliance.gst_india.doctype.gst_invoice_management_system import (
            IMSReconciler,
        )

        # Auto_Reconcile Invoices
        IMSReconciler().auto_reconcile_invoices(
            frappe._dict({"company": company, "company_gstin": company_gstin})
        )

        frappe.publish_realtime(
            "ims_download_completed",
            message={"message": _("Downloaded and Reconciled Invoices successfully")},
            user=frappe.session.user,
        )


def save_ims_invoices(company_gstin, return_period, json_data):
    from india_compliance.gst_india.doctype.gst_invoice_management_system import (
        IMSReconciler,
    )

    company = get_party_for_gstin(company_gstin, "Company")
    for category in IMS_CATEGORIES:
        if not json_data.get(category):
            continue

        getattr(ims, category.upper())(company_gstin, company).create_transactions(
            json_data.get(category)
        )

    # Auto_Reconcile Invoices
    IMSReconciler().auto_reconcile_invoices(
        frappe._dict({"company": company, "company_gstin": company_gstin})
    )


def reset_previous_ims_action():
    inward_supply = frappe.qb.DocType("GST Inward Supply")

    frappe.qb.update(inward_supply).set(inward_supply.previous_ims_action, "").run()
