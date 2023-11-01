from enum import Enum

import frappe
from frappe import _
from frappe.query_builder.terms import Criterion
from frappe.utils import cint

from india_compliance.gst_india.api_classes.returns import (
    GSTR2aAPI,
    GSTR2bAPI,
    ReturnsAPI,
)
from india_compliance.gst_india.doctype.gstr_import_log.gstr_import_log import (
    create_import_log,
    toggle_scheduled_jobs,
)
from india_compliance.gst_india.utils import get_party_for_gstin
from india_compliance.gst_india.utils.gstr import gstr_2a, gstr_2b


class ReturnType(Enum):
    GSTR2A = "GSTR2a"
    GSTR2B = "GSTR2b"


class GSTRCategory(Enum):
    B2B = "B2B"
    B2BA = "B2BA"
    CDNR = "CDNR"
    CDNRA = "CDNRA"
    ISD = "ISD"
    ISDA = "ISDA"
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

GSTR_MODULES = {
    ReturnType.GSTR2A.value: gstr_2a,
    ReturnType.GSTR2B.value: gstr_2b,
}

IMPORT_CATEGORY = ("IMPG", "IMPGSEZ")


def download_gstr_2a(gstin, return_periods, otp=None):
    total_expected_requests = len(return_periods) * len(ACTIONS)
    requests_made = 0
    queued_message = False
    settings = frappe.get_cached_doc("GST Settings")

    return_type = ReturnType.GSTR2A
    api = GSTR2aAPI(gstin)
    for return_period in return_periods:
        is_last_period = return_periods[-1] == return_period

        json_data = frappe._dict({"gstin": gstin, "fp": return_period})
        for action, category in ACTIONS.items():
            requests_made += 1

            if (
                not settings.enable_overseas_transactions
                and category.value in IMPORT_CATEGORY
            ):
                continue

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

            response = api.get_data(action, return_period, otp)
            if response.error_type in ["otp_requested", "invalid_otp"]:
                return response

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

        save_gstr_2a(gstin, return_period, json_data)

    if queued_message:
        show_queued_message()


def download_gstr_2b(gstin, return_periods, otp=None):
    total_expected_requests = len(return_periods)
    requests_made = 0
    queued_message = False

    api = GSTR2bAPI(gstin)
    for return_period in return_periods:
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

        # TODO: skip if today is not greater than 14th return period's next months
        response = api.get_data(return_period, otp)
        if response.error_type in ["otp_requested", "invalid_otp"]:
            return response

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

        # Handle multiple files for GSTR2B
        if response.data and (file_count := response.data.get("fc")):
            for file_num in range(1, file_count + 1):
                r = api.get_data(return_period, otp, file_num)
                save_gstr_2b(gstin, return_period, r)

            continue  # skip first response if file_count is greater than 1

        save_gstr_2b(gstin, return_period, response)

    if queued_message:
        show_queued_message()


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


def save_gstr(gstin, return_type, return_period, json_data, gen_date_2b=None):
    frappe.enqueue(
        _save_gstr,
        queue="long",
        now=frappe.flags.in_test,
        timeout=1800,
        gstin=gstin,
        return_type=return_type.value,
        return_period=return_period,
        json_data=json_data,
        gen_date_2b=gen_date_2b,
    )


def _save_gstr(gstin, return_type, return_period, json_data, gen_date_2b=None):
    """Save GSTR data to Inward Supply

    :param return_period: str
    :param json_data: dict of list (GSTR category: suppliers)
    :param gen_date_2b: str (Date when GSTR 2B was generated)
    """

    company = get_party_for_gstin(gstin, "Company")
    for category in GSTRCategory:
        gstr = get_data_handler(return_type, category)
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


GSTR_FUNCTIONS = {
    ReturnType.GSTR2A.value: _download_gstr_2a,
    ReturnType.GSTR2B.value: save_gstr_2b,
}


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
    try:
        api = ReturnsAPI(doc.gstin)
        response = api.download_files(
            doc.return_period,
            doc.request_id,
        )

    except Exception as e:
        frappe.db.delete("GSTR Import Log", {"name": doc.name})
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


def show_queued_message():
    frappe.msgprint(
        _(
            "Some returns are queued for download at GSTN as there may be large data."
            " We will retry download every few minutes until it succeeds.<br><br>"
            "You can track download status from download dialog."
        )
    )
