# Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import json

import frappe
from frappe import _
from frappe.utils import flt, getdate

from india_compliance.gst_india.utils.gstr_1 import GSTR1_SubCategory
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
        {
            "fieldname": "invoice_type",
            "label": _("Invoice Type"),
            "fieldtype": "Data",
            "width": 120,
            "hidden": not filters.get("bifurcate_hsn"),
        },
    ]

    return columns


def get_hsn_data(filters):
    _class = GSTR1Invoices(filters)
    invoices = _class.get_invoices_for_item_wise_summary()
    _class.process_invoices(invoices, filters.get("bifurcate_hsn"))

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

    hsn_summary = GSTR1BooksData({}).prepare_hsn_data(invoices)

    hsn_data = []
    for hsn_key in hsn_summary.values():
        hsn_data.extend(list(hsn_key.values()))

    return [
        {
            **row,
            "uom": map_uom(row["uom"], row),
            "invoice_type": row["document_type"].split("-")[-1].strip(),
            **{field: flt(row[field], 2) for field in precision_fields},
        }
        for row in hsn_data
    ]


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

    gst_json["hsn"] = get_hsn_wise_json_data(report_data, filters)

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


def get_hsn_wise_json_data(report_data, filters):
    hsn_b2b = []
    hsn_b2c = []
    hsn_data = []

    for count, hsn in enumerate(report_data, start=1):
        if hsn.get("hsn_code") == "Total":
            continue

        if not hsn.get("hsn_code"):
            frappe.throw(
                _(
                    "GST HSN Code is missing in one or more invoices. Please ensure all invoices include the HSN Code, as it is Mandatory for filing GSTR-1."
                )
            )

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

        # Bifurcate by B2B and B2C only if the filter is set
        if not filters.get("bifurcate_hsn"):
            hsn_data.append(row)
            continue

        if hsn["document_type"] == GSTR1_SubCategory.HSN_B2B.value:
            hsn_b2b.append(row)
        else:
            hsn_b2c.append(row)

    if filters.get("bifurcate_hsn"):
        return {
            "hsn_b2b": hsn_b2b,
            "hsn_b2c": hsn_b2c,
        }

    return {"data": hsn_data}


def map_uom(uom, data=None):
    uom = uom.upper()

    if "-" in uom:
        if (
            data
            and (hsn_code := data.get("hsn_code") or "")
            and hsn_code.startswith("99")
        ):
            return "NA"

        return uom.split("-")[0]

    return uom
