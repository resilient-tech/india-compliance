from enum import Enum

import frappe
from frappe import _
from frappe.query_builder.terms import Criterion

from india_compliance.gst_india.api_classes.returns import GSTR2aAPI, GSTR2bAPI
from india_compliance.gst_india.doctype.gstr_import_log.gstr_import_log import (
    create_import_log,
)
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
    ReturnType.GSTR2A: gstr_2a,
    ReturnType.GSTR2B: gstr_2b,
}


def download_gstr_2a(gstin, return_periods, otp=None):
    total_expected_requests = len(return_periods) * len(ACTIONS)
    requests_made = 0

    return_type = ReturnType.GSTR2A
    api = GSTR2aAPI(gstin)
    for return_period in return_periods:
        is_last_period = return_periods[-1] == return_period

        json_data = frappe._dict({"gstin": gstin, "fp": return_period})
        for action, category in ACTIONS.items():
            requests_made += 1
            frappe.publish_realtime(
                "update_api_progress",
                {
                    "current_progress": requests_made * 100 / total_expected_requests,
                    "return_period": return_period,
                    "is_last_period": is_last_period,
                },
            )

            # call api only if data is available

            if frappe.db.get_value(
                "GSTR Import Log",
                {
                    "gstin": gstin,
                    "return_type": return_type.value,
                    "return_period": return_period,
                    "classification": category.value,
                },
                "data_not_found",
            ):
                continue

            response = api.get_data(action, return_period, otp)
            if response.error_type == "otp_requested":
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

            if response.error_type:
                continue

            if not (data := response.get(action.lower())):
                frappe.throw(
                    _(
                        "Data received seems to be invalid from the GST Portal. Please try"
                        " again or raise support ticket."
                    ),
                    title="Invalid Response Received.",
                )

            # making consistent with GSTR2a upload
            json_data[action.lower()] = data

        save_gstr_2a(gstin, return_period, json_data)


def download_gstr_2b(gstin, return_periods, otp=None):
    api = GSTR2bAPI(gstin)
    for return_period in return_periods:
        # TODO: skip if today is not greater than 14th return period's next months
        response = api.get_data(return_period, otp)
        if response.error_type == "otp_requested":
            return response

        if response.error_type == "no_docs_found":
            create_import_log(
                gstin, ReturnType.GSTR2B.value, return_period, data_not_found=True
            )
            continue

        if response.error_type:
            continue

        save_gstr_2b(gstin, return_period, response)

    update_import_history(return_periods)


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
            title="Invalid Response Received.",
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
    if (
        not json_data
        or json_data.get("gstin") != gstin
        or json_data.get("rtnprd") != return_period
    ):
        frappe.throw(
            _(
                "Data received seems to be invalid from the GST Portal. Please try"
                " again or raise support ticket."
            ),
            title="Invalid Response Received.",
        )

    create_import_log(gstin, return_type.value, return_period)
    save_gstr(
        gstin,
        return_type,
        return_period,
        json_data.get("docdata"),
        json_data.get("gendt"),
    )


def save_gstr(gstin, return_type, return_period, json_data, gen_date_2b=None):
    frappe.enqueue(
        _save_gstr,
        queue="short",
        now=frappe.flags.in_test,
        gstin=gstin,
        return_type=return_type,
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
    for category in GSTRCategory:
        gstr = get_data_handler(return_type, category)
        gstr(gstin, return_period, json_data, gen_date_2b).create_transactions(
            category,
            json_data.get(category.value.lower()),
        )


def get_data_handler(return_type, category):
    class_name = return_type.value + category.value
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
