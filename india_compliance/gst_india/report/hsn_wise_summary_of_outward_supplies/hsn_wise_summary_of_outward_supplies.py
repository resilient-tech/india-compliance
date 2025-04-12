# Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import json

import frappe
from frappe import _
from frappe.utils import flt, getdate

from india_compliance.gst_india.utils.gstr_1.gstr_1_data import GSTR1Invoices


def execute(filters=None):
    if not filters:
        filters = {}

    validate_filters(filters)

    columns = get_columns(filters)
    data = get_hsn_data(filters)

    return columns, data


def validate_filters(filters):
    from_date, to_date = filters.get("from_date"), filters.get("to_date")

    if from_date and to_date and getdate(to_date) < getdate(from_date):
        frappe.throw(_("To Date cannot be less than From Date"))


def get_columns(filters):
    company_currency = frappe.get_cached_value(
        "Company", filters.get("company"), "default_currency"
    )

    columns = [
        {
            "fieldname": "hsn_code",
            "label": _("HSN"),
            "fieldtype": "Link",
            "options": "GST HSN Code",
            "width": 100,
        },
        {
            "fieldname": "description",
            "label": _("Description"),
            "fieldtype": "Data",
            "width": 300,
        },
        {
            "fieldname": "uom",
            "label": _("UQC"),
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "fieldname": "quantity",
            "label": _("Total Quantity"),
            "fieldtype": "Float",
            "width": 90,
        },
        {
            "fieldname": "document_value",
            "label": _("Total Value"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 120,
        },
        {
            "fieldname": "tax_rate",
            "label": _("Rate"),
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "fieldname": "total_taxable_value",
            "label": _("Taxable Value"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 170,
        },
        {
            "fieldname": "total_igst_amount",
            "label": _("Integrated Tax Amount"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 170,
        },
        {
            "fieldname": "total_cgst_amount",
            "label": _("Central Tax Amount"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 170,
        },
        {
            "fieldname": "total_sgst_amount",
            "label": _("State/UT Tax Amount"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 170,
        },
        {
            "fieldname": "total_cess_amount",
            "label": _("Cess Amount"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 170,
        },
    ]

    return columns


def get_hsn_data(filters):
    _class = GSTR1Invoices(filters)
    invoices = _class.get_invoices_for_item_wise_summary()
    _class.process_invoices(invoices)

    return process_hsn_data(invoices)


def process_hsn_data(invoices):
    # TODO: This import should be moved to the top of the file once GSTR-1 Report is discontinued.
    from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import GSTR1BooksData

    precision_fields = (
        "quantity",
        "document_value",
        "tax_rate",
        "total_taxable_value",
        "total_igst_amount",
        "total_cgst_amount",
        "total_sgst_amount",
        "total_cess_amount",
    )

    hsn_data = GSTR1BooksData({}).prepare_hsn_data(invoices)

    return [
        {
            **row,
            "uom": row["uom"].split("-")[0],
            **{field: flt(row[field], 2) for field in precision_fields},
        }
        for row in hsn_data.values()
    ]


# TODO: This function will be unused and should be removed once GSTR-1 Report is discontinued.
def get_conditions(filters):
    conditions = ""

    for opts in (
        ("company", " and company=%(company)s"),
        ("gst_hsn_code", " and gst_hsn_code=%(gst_hsn_code)s"),
        ("company_gstin", " and company_gstin=%(company_gstin)s"),
        ("from_date", " and posting_date >= %(from_date)s"),
        ("to_date", " and posting_date <= %(to_date)s"),
    ):
        if filters.get(opts[0]):
            conditions += opts[1]

    return conditions


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

    gst_json = {"version": "GST3.1.2", "hash": "hash", "gstin": gstin, "fp": fp}

    gst_json["hsn"] = get_hsn_wise_json_data(report_data)

    return {"report_name": report_name, "data": gst_json}


@frappe.whitelist()
def download_json_file():
    """download json content in a file"""
    data = frappe._dict(frappe.local.form_dict)
    frappe.response["filename"] = (
        frappe.scrub("{0}".format(data["report_name"])) + ".json"
    )
    frappe.response["filecontent"] = data["data"]
    frappe.response["content_type"] = "application/json"
    frappe.response["type"] = "download"


def get_hsn_wise_json_data(report_data):
    data = []
    count = 1

    for hsn in report_data:
        if hsn.get("hsn_code") == "Total":
            continue
        row = {
            "num": count,
            "hsn_sc": hsn.get("hsn_code"),
            "uqc": hsn.get("uom"),
            "qty": hsn.get("quantity"),
            "rt": hsn.get("tax_rate"),
            "txval": hsn.get("total_taxable_value"),
            "iamt": 0.0,
            "camt": 0.0,
            "samt": 0.0,
            "csamt": 0.0,
        }

        if hsn_description := hsn.get("description"):
            row["desc"] = hsn_description[:30]

        row["iamt"] += hsn.get("total_igst_amount")
        row["camt"] += hsn.get("total_cgst_amount")
        row["samt"] += hsn.get("total_sgst_amount")
        row["csamt"] += hsn.get("total_cess_amount")

        data.append(row)
        count += 1

    return {"data": data}
