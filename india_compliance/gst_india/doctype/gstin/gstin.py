# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt
from datetime import datetime

import frappe
from frappe.model.document import Document
from frappe.utils import date_diff

from india_compliance.gst_india.utils.gstin_info import (
    get_gstin_e_invoice_api,
    get_gstin_public_api,
)


class GSTIN(Document):
    pass


def create_gstin(**kwargs):
    gstin_exists = frappe.db.exists("GSTIN", kwargs.get("gstin"))
    if gstin_exists:
        doc = frappe.get_doc("GSTIN", kwargs.pop("gstin"))
    else:
        doc = frappe.new_doc("GSTIN")

    doc.update({**kwargs, "last_updated_on": datetime.now()})
    doc.save(ignore_permissions=True)


@frappe.whitelist()
def get_gstin_status(gstin):
    return frappe.get_value("GSTIN", gstin, "status")


@frappe.whitelist()
def get_gstin(gstin):
    gstin_detail = frappe.db.get("GSTIN", gstin)
    gst_settings = frappe.get_cached_doc("GST Settings")

    if not gstin_detail:
        gstin_detail = update_gstin_details(gstin)

    if gst_settings.gstin_status_refresh_interval == 0:
        return gstin_detail

    days_since_update = date_diff(
        datetime.now(), gstin_detail.get("last_updated_on", datetime.now())
    )
    if days_since_update >= gst_settings.gstin_status_refresh_interval:
        gstin_detail = update_gstin_details(gstin)

    return gstin_detail


def get_company_gstin():
    gst_settings = frappe.get_cached_doc("GST Settings")
    company_gstin = None
    for row in gst_settings.credentials:
        if row.service == "e-Waybill / e-Invoice":
            company_gstin = row.gstin
    return company_gstin, gst_settings


def update_gstin_details(gstin):
    company_gstin, gst_settings = get_company_gstin()

    if company_gstin and gst_settings.enable_e_invoice:
        gstin_detail = get_gstin_e_invoice_api(company_gstin, gstin)
    else:
        gstin_detail = get_gstin_public_api(gstin)

    create_gstin(**gstin_detail)
    return gstin_detail
