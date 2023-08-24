# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, format_date, get_datetime

from india_compliance.gst_india.api_classes.e_invoice import EInvoiceAPI
from india_compliance.gst_india.api_classes.public import PublicAPI
from india_compliance.gst_india.utils import is_api_enabled, parse_datetime

GSTIN_STATUS = {
    "ACT": "Active",
    "CNL": "Cancelled",
    "INA": "Inactive",
    "PRO": "Provisional",
}

GSTIN_BLOCK_STATUS = {"U": 0, "B": 1}


class GSTIN(Document):
    def before_save(self):
        self.status = GSTIN_STATUS.get(self.status, self.status)
        self.is_blocked = GSTIN_BLOCK_STATUS.get(self.is_blocked, 0)
        self.last_updated_on = get_datetime()

        self.registration_date = parse_datetime(
            self.registration_date, day_first=True, throw=False
        )

        self.cancelled_date = parse_datetime(
            self.cancelled_date, day_first=True, throw=False
        )

        if not self.cancelled_date and self.status == "Cancelled":
            self.cancelled_date = self.registration_date

    @frappe.whitelist()
    def update_gstin_status(self):
        create_or_update_gstin_status(self.gstin, doc=self)


@frappe.whitelist()
def get_gstin_status(gstin, transaction_date=None, is_request_from_ui=0):
    if not is_status_refresh_required(gstin):
        if not frappe.db.exists("GSTIN", gstin):
            return

        return frappe.get_doc("GSTIN", gstin)

    return get_updated_gstin(gstin, transaction_date, is_request_from_ui)


def get_updated_gstin(gstin, transaction_date=None, is_request_from_ui=0):
    if is_request_from_ui:
        return create_or_update_gstin_status(gstin)

    return frappe.enqueue(
        create_or_update_gstin_status,
        enqueue_after_commit=True,
        queue="short",
        gstin=gstin,
        transaction_date=transaction_date,
        callback=_validate_gstin_info,
    )


def create_or_update_gstin_status(
    gstin=None,
    response=None,
    transaction_date=None,
    callback=None,
):
    doctype = "GSTIN"
    response = _get_gstin_info(gstin=gstin, response=response)

    if not response:
        return

    if frappe.db.exists(doctype, response.get("gstin")):
        doc = frappe.get_doc(doctype, response.pop("gstin"))
    else:
        doc = frappe.new_doc(doctype)

    doc.update(response)
    doc.save(ignore_permissions=True)

    if callback:
        callback(doc, transaction_date)

    return doc


def _get_gstin_info(*, gstin=None, response=None):
    if response:
        return get_formatted_response(response)

    try:
        company_gstin = get_company_gstin()

        if not company_gstin:
            response = PublicAPI().get_gstin_info(gstin)
            return get_formatted_response(response)

        response = EInvoiceAPI(company_gstin=company_gstin).get_gstin_info(gstin)
        return frappe._dict(
            {
                "gstin": gstin,
                "registration_date": response.DtReg,
                "cancelled_date": response.DtDReg,
                "status": response.Status,
                "is_blocked": response.BlkStatus,
            }
        )

    except Exception:
        frappe.log_error(
            title=_("Error fetching GSTIN status"),
            message=frappe.get_traceback(),
        )

    finally:
        frappe.cache.set_value(gstin, True, expires_in_sec=180)


def _validate_gstin_info(gstin_doc, transaction_date=None, throw=False):
    if not (gstin_doc and transaction_date):
        return

    def _throw(message):
        # TODO: Is throw required for all errors? Improve error messages
        if throw:
            frappe.throw(message)

        else:
            frappe.log_error(
                title=_("Invalid Party GSTIN"),
                message=message,
            )

    registration_date = gstin_doc.registration_date
    cancelled_date = gstin_doc.cancelled_date

    if not registration_date:
        return _throw(
            _(
                "Registration date not found for Party GSTIN. Please make sure that if GSTIN is registered."
            )
        )

    if date_diff(transaction_date, registration_date) < 0:
        return _throw(
            _(
                "Party GSTIN is Registered on {0}. Please make sure that document date is on or after {0}"
            ).format(format_date(registration_date))
        )

    if (
        gstin_doc.status == "Cancelled"
        and date_diff(transaction_date, cancelled_date) >= 0
    ):
        return _throw(
            _(
                "Party GSTIN is Cancelled on {0}. Please make sure that document date is before {0}"
            ).format(format_date(cancelled_date))
        )

    if gstin_doc.status not in ("Active", "Cancelled"):
        return _throw(_("Status of Party GSTIN is {0}").format(gstin_doc.status))


def get_company_gstin():
    gst_settings = frappe.get_cached_doc("GST Settings")

    if not gst_settings.enable_e_invoice:
        return

    for row in gst_settings.credentials:
        if row.service == "e-Waybill / e-Invoice":
            return row.gstin


def is_status_refresh_required(gstin):
    settings = frappe.get_cached_doc("GST Settings")

    if (
        not settings.gstin_status_refresh_interval
        or not is_api_enabled(settings)
        or settings.sandbox_mode
        or frappe.cache.get_value(gstin)
    ):
        return

    doc = frappe.db.get_value(
        "GSTIN", gstin, ["last_updated_on", "status"], as_dict=True
    )

    if not doc or doc.status not in ("Active", "Cancelled"):
        return True

    days_since_last_update = date_diff(get_datetime(), doc.get("last_updated_on"))
    return days_since_last_update >= settings.gstin_status_refresh_interval


def get_formatted_response(response):
    """
    Format response from Public API
    """
    return frappe._dict(
        {
            "gstin": response.gstin,
            "registration_date": response.rgdt,
            "cancelled_date": response.cxdt,
            "status": response.sts,
        }
    )
