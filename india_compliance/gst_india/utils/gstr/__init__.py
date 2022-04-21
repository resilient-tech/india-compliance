from datetime import datetime
from enum import Enum

import frappe

from india_compliance.gst_india.api_classes.returns import GSTR2aAPI, GSTR2bAPI
from india_compliance.gst_india.doctype.gstr_download_log.gstr_download_log import (
    create_download_log,
)
from india_compliance.gst_india.utils.gstr import gstr_2a, gstr_2b


class ICEnum(Enum):
    @classmethod
    def as_dict(cls):
        return frappe._dict({member.name: member.value for member in cls})


class ReturnType(ICEnum):
    GSTR2A = "GSTR2a"
    GSTR2B = "GSTR2b"


class GSTRCategory(ICEnum):
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

MODULE_MAP = {
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
                    "gst_return": ReturnType.GSTR2A.value,
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
            if not response.get(action.lower()):
                frappe.throw(
                    "Data received seems to be invalid from the GST Portal. Please try"
                    " again or raise support ticket.",
                    title="Invalid Response Received.",
                )

            json_data.update(response)

        save_gstr(gstin, ReturnType.GSTR2A, return_period, json_data)


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

        json_data = response.data

        # TODO: confirm about throwing
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

        save_gstr(gstin, ReturnType.GSTR2B, return_period, json_data.get("docdata"))


def save_gstr(gstin, return_type, return_period, json_data):
    """Save GSTR data to Inward Supply

    :param return_period: str
    :param json_data: dict of list (GSTR category: suppliers)
    """
    create_download_log(gstin, return_type.value, return_period)

    for category in GSTRCategory:
        data_handler = get_data_handler(return_type, category)(gstin, return_period)
        data_handler.create_transactions(
            category,
            json_data.get(category.value.lower()),
        )


def get_data_handler(return_type, category):
    return getattr(MODULE_MAP[return_type], f"{return_type.value}{category.value}")
