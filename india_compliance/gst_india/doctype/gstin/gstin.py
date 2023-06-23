# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt
from datetime import datetime

import frappe
from frappe.model.document import Document
from frappe.utils import date_diff

from india_compliance.gst_india.api_classes.e_invoice import EInvoiceAPI
from india_compliance.gst_india.api_classes.public import PublicAPI
from india_compliance.gst_india.utils import parse_datetime


class GSTIN(Document):
    pass


def create_gstin(gstin, status, registration_date, cancelled_date, block_status=None):
    gstin_exists = frappe.db.exists("GSTIN", gstin)

    if gstin_exists:
        gstin_detail = {
            "status": status,
            "registration_date": registration_date,
            "last_updated_on": datetime.now(),
            "cancelled_date": cancelled_date,
            "block_status": block_status,
        }
        frappe.get_doc("GSTIN", gstin).update(gstin_detail).save()
    else:
        gstin_detail = frappe.new_doc("GSTIN")
        gstin_detail.gstin = gstin
        gstin_detail.status = status
        gstin_detail.registration_date = registration_date
        gstin_detail.last_updated_on = datetime.now()
        gstin_detail.cancelled_date = cancelled_date
        gstin_detail.block_status = block_status
        gstin_detail.insert()


@frappe.whitelist()
def get_gstin_status(gstin):
    return frappe.get_value("GSTIN", gstin, "status")


@frappe.whitelist()
def get_gstin(gstin):
    gstin_detail = frappe.db.get("GSTIN", gstin)
    if not gstin_detail:
        fetch_gstin_details(gstin)
        gstin_detail = frappe.db.get("GSTIN", gstin)

    days_since_update = date_diff(
        datetime.now(), gstin_detail.get("last_updated_on", datetime.now())
    )
    if days_since_update >= 60:
        gstin_detail.status = fetch_gstin_details(gstin)

    return gstin_detail


def fetch_gstin_details(gstin):
    GSTIN_STATUS = {"ACT": "Active", "CNL": "Cancelled"}

    gst_settings = frappe.get_cached_doc("GST Settings")
    company_gstin = None
    for row in gst_settings.credentials:
        if row.service == "e-Waybill / e-Invoice":
            company_gstin = row.gstin

    if company_gstin and gst_settings.enable_e_invoice:
        response = EInvoiceAPI(company_gstin=company_gstin).get_gstin_info(gstin)
        registration_date = parse_datetime(response.DtReg, day_first=True)
        cancelled_date = response.DtDReg
        status = GSTIN_STATUS.get(response.Status, response.Status)
        block_status = response.BlkStatus
    else:
        response = PublicAPI().get_gstin_info(gstin)
        registration_date = parse_datetime(response.rgdt, day_first=True)
        cancelled_date = response.cxdt
        status = response.sts
        block_status = None

    try:
        cancelled_date = parse_datetime(cancelled_date, day_first=True)
    except Exception:
        cancelled_date = registration_date if status == "Cancelled" else None

    create_gstin(
        gstin=gstin,
        status=status,
        registration_date=registration_date,
        cancelled_date=cancelled_date,
        block_status=block_status,
    )

    return status
