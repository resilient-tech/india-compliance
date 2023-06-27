# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import date_diff, get_datetime

from india_compliance.gst_india.api_classes.e_invoice import EInvoiceAPI
from india_compliance.gst_india.api_classes.public import PublicAPI
from india_compliance.gst_india.utils import parse_datetime

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
        self.block_status = GSTIN_BLOCK_STATUS.get(self.block_status, self.block_status)

        try:
            self.cancelled_date = parse_datetime(self.cancelled_date, day_first=True)

        except Exception:
            self.cancelled_date = (
                self.registration_date if self.status == "Cancelled" else None
            )

        self.last_updated_on = get_datetime()


@frappe.whitelist()
def get_gstin_status(gstin):
    gstin_refresh_interval = frappe.get_cached_value(
        "GST Settings", None, "gstin_status_refresh_interval"
    )

    if not gstin_refresh_interval:
        return

    gstin_doc = get_updated_gstin(gstin, gstin_refresh_interval)
    return frappe._dict(
        {
            "status": gstin_doc.get("status"),
            "registration_date": gstin_doc.get("registration_date"),
            "cancelled_date": gstin_doc.get("cancelled_date"),
        }
    )


def get_updated_gstin(gstin, gstin_refresh_interval):
    if not frappe.db.exists("GSTIN", gstin):
        return create_or_update_gstin_status(gstin)

    gstin_doc = frappe.get_doc("GSTIN", gstin)

    days_since_update = date_diff(get_datetime(), gstin_doc.get("last_updated_on"))
    if days_since_update >= gstin_refresh_interval:
        return create_or_update_gstin_status(gstin)

    return gstin_doc


def create_or_update_gstin_status(gstin=None, response=None):
    if not response:
        response = _get_gstin_status(gstin=gstin, company_gstin=get_company_gstin())
    else:
        response = get_formatted_response(response)

    gstin_exists = frappe.db.exists("GSTIN", response.get("gstin"))
    if gstin_exists:
        doc = frappe.get_doc("GSTIN", response.pop("gstin"))
    else:
        doc = frappe.new_doc("GSTIN")

    doc.update(response)
    doc.save(ignore_permissions=True)

    return doc


def _get_gstin_status(*, gstin, company_gstin=None):
    if not company_gstin:
        response = PublicAPI().get_gstin_info(gstin)
        return get_formatted_response(response)

    response = EInvoiceAPI(company_gstin=company_gstin).get_gstin_info(gstin)
    return frappe._dict(
        {
            "gstin": gstin,
            "registration_date": parse_datetime(response.DtReg, day_first=True),
            "cancelled_date": response.DtDReg,
            "status": response.Status,
            "block_status": response.BlkStatus,
        }
    )


def get_formatted_response(response):
    return frappe._dict(
        {
            "gstin": response.gstin,
            "registration_date": parse_datetime(response.rgdt, day_first=True),
            "cancelled_date": response.cxdt,
            "status": response.sts,
        }
    )


def get_company_gstin():
    gst_settings = frappe.get_cached_doc("GST Settings")

    if not gst_settings.enable_e_invoice:
        return

    for row in gst_settings.credentials:
        if row.service == "e-Waybill / e-Invoice":
            return row.gstin
