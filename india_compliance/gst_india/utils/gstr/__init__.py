from enum import Enum

import frappe
from frappe.query_builder.terms import Criterion

from india_compliance.gst_india.api_classes.returns import GSTR2aAPI, GSTR2bAPI
from india_compliance.gst_india.doctype.gstr_download_log.gstr_download_log import (
    create_download_log,
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
    api = GSTR2aAPI(gstin)
    for return_period in return_periods:
        json_data = {}
        for action, category in ACTIONS.items():
            # call api only if data is available
            if frappe.db.get_value(
                "GSTR Download Log",
                {
                    "return_type": ReturnType.GSTR2A.value,
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
                create_download_log(
                    gstin,
                    ReturnType.GSTR2A.value,
                    return_period,
                    classification=category.value,
                    data_not_found=True,
                )
                continue

            # TODO: confirm about throwing
            if not (data := response.get(action.lower())):
                frappe.throw(
                    "Data received seems to be invalid from the GST Portal. Please try"
                    " again or raise support ticket.",
                    title="Invalid Response Received.",
                )

            # making consistent with GSTR2b
            json_data[category.value] = data

        save_gstr_2a(gstin, return_period, json_data)


def download_gstr_2b(gstin, return_periods, otp=None):
    api = GSTR2bAPI(gstin)
    for return_period in return_periods:
        response = api.get_data(return_period, otp)
        if response.error_type == "otp_requested":
            return response

        if response.error_type == "no_docs_found":
            create_download_log(
                gstin, ReturnType.GSTR2B.value, return_period, data_not_found=True
            )
            continue

        save_gstr_2b(gstin, return_period, response)

    update_download_history(return_periods)


def save_gstr_2a(gstin, return_period, json_data):
    return save_gstr(gstin, ReturnType.GSTR2A, return_period, json_data)


def save_gstr_2b(gstin, return_period, json_data):
    json_data = json_data.data
    if (
        not json_data
        or json_data.get("gstin") != gstin
        or json_data.get("rtnprd") != return_period
    ):
        frappe.throw(
            "Data received seems to be invalid from the GST Portal. Please try"
            " again or raise support ticket.",
            title="Invalid Response Received.",
        )

    return save_gstr(gstin, ReturnType.GSTR2B, return_period, json_data.get("docdata"))


# TODO: enqueue save_gstr
# TODO: show progress
def save_gstr(gstin, return_type, return_period, json_data):
    """Save GSTR data to Inward Supply

    :param return_period: str
    :param json_data: dict of list (GSTR category: suppliers)
    """
    create_download_log(gstin, return_type.value, return_period)

    for category in GSTRCategory:
        gstr = get_data_handler(return_type, category)
        gstr(gstin, return_period, json_data).create_transactions(
            category,
            json_data.get(category.value.lower()),
        )


def get_data_handler(return_type, category):
    class_name = return_type.value + category.value
    return getattr(GSTR_MODULES[return_type], class_name)


def update_download_history(return_periods):

    """Updates 2A data availability from 2B download"""

    if not (
        inward_supplies := frappe.get_all(
            "Inward Supply",
            filters={"return_period_2b": ("in", return_periods)},
            fields=("sup_return_period as return_period", "classification"),
            distinct=True,
        )
    ):
        return

    log = frappe.qb.DocType("GSTR Download Log")
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
