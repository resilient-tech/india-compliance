# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt
import json

import frappe
from frappe import _
from frappe.utils import getdate

from india_compliance.gst_india.report.hsn_wise_summary_of_outward_supplies.hsn_wise_summary_of_outward_supplies import (
    get_columns,
    process_hsn_data,
    validate_filters,
)
from india_compliance.gst_india.utils.gstr3b.gstr3b_data import GSTR3BInvoices


def execute(filters=None):
    if not filters:
        filters = {}

    validate_filters(filters)

    columns = get_columns(filters)
    data = get_data(filters)

    return columns, data


def get_data(filters):
    _class = GSTR3BInvoices(filters)
    invoices = []

    for doctype in ("Purchase Invoice", "Bill of Entry"):
        invoices.extend(_class.get_data(doctype))

    return process_hsn_data(invoices)


@frappe.whitelist()
def get_json(filters, report_name, data):
    from india_compliance.gst_india.report.gstr_1.gstr_1 import get_company_gstin_number

    filters = json.loads(filters)
    report_data = json.loads(data)
    gstin = filters.get("company_gstin") or get_company_gstin_number(filters["company"])

    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.throw(_("Please enter From Date and To Date to generate JSON"))

    fp = "%02d%s" % (
        getdate(filters["to_date"]).month,
        getdate(filters["to_date"]).year,
    )

    gst_json = {"gstin": gstin, "fp": fp}
    gst_json["table18"] = get_hsn_wise_json_data(report_data)

    return {"report_name": report_name, "data": gst_json}


def get_hsn_wise_json_data(report_data):
    data = []

    for hsn in report_data:
        if hsn.get("hsn_code") == "Total":
            continue

        row = {
            "hsn_sc": hsn.get("hsn_code"),
            "uqc": hsn.get("uom"),
            "qty": hsn.get("quantity"),
            "rt": hsn.get("tax_rate"),
            "txval": hsn.get("total_taxable_value"),
            "iamt": 0.0,
            "camt": 0.0,
            "samt": 0.0,
            "csamt": 0.0,
            "isconcesstional": "N",  # TODO: How to identify concession
        }

        if hsn_description := hsn.get("description"):
            row["desc"] = hsn_description[:1000]  # Character limit for GSTR-9 upload

        row["iamt"] += hsn.get("total_igst_amount")
        row["camt"] += hsn.get("total_cgst_amount")
        row["samt"] += hsn.get("total_sgst_amount")
        row["csamt"] += hsn.get("total_cess_amount")

        data.append(row)

    return {"items": data}
