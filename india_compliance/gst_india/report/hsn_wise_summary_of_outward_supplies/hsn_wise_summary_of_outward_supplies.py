# Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import json

import frappe
from frappe import _
from frappe.utils import flt, getdate

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.utils import get_gst_uom


def execute(filters=None):
    if not filters:
        filters = {}

    validate_filters(filters)

    columns = get_columns(filters)

    data = get_hsn_data(filters, columns)

    return columns, data


def get_hsn_data(filters, columns):
    item_list = get_items(filters)

    data = []
    added_item = set()

    for d in item_list:
        item_key = d.item_code or d.item_name
        key = (d.parent, d.gst_hsn_code, item_key, d.uqc)
        if key in added_item:
            continue

        if d.gst_hsn_code.startswith("99"):
            # service item doesn't have qty/uom
            d.qty = 0
            d.uqc = "NA"
        else:
            d.uqc = get_gst_uom(d.get("uqc"))

        total_tax = 0

        for tax in GST_TAX_TYPES:
            total_tax += flt(d.get(f"{tax}_amount"), 2)

        d.taxable_value = flt(d.taxable_value, 2)
        row = {
            "gst_hsn_code": d.gst_hsn_code,
            "description": d.description,
            "uqc": d.uqc,
            "qty": flt(d.qty, 2),
            "total_amount": flt(d.taxable_value + total_tax, 2),
            "tax_rate": flt(d.get("tax_rate", 0)),
            "taxable_amount": d.taxable_value,
        }

        for tax in GST_TAX_TYPES[:-1]:
            if tax == "cess":
                cess_amount = flt(
                    d.get("cess_amount", 0) + d.get("cess_non_advol_amount", 0), 2
                )
                row["cess_account"] = cess_amount
            else:
                row[f"{tax}_account"] = flt(d.get(f"{tax}_amount", 0), 2)

        data.append(row)
        added_item.add(key)

    if data:
        data = get_merged_data(columns, data)  # merge same hsn code data

    return data


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
            "fieldname": "gst_hsn_code",
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
            "fieldname": "uqc",
            "label": _("UQC"),
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "fieldname": "qty",
            "label": _("Total Quantity"),
            "fieldtype": "Float",
            "width": 90,
        },
        {
            "fieldname": "total_amount",
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
            "fieldname": "taxable_amount",
            "label": _("Taxable Value"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 170,
        },
        {
            "fieldname": "igst_account",
            "label": _("Integrated Tax Amount"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 170,
        },
        {
            "fieldname": "cgst_account",
            "label": _("Central Tax Amount"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 170,
        },
        {
            "fieldname": "sgst_account",
            "label": _("State/UT Tax Amount"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 170,
        },
        {
            "fieldname": "cess_account",
            "label": _("Cess Amount"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 170,
        },
    ]

    return columns


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


def get_tax_fields():
    return ", ".join(
        f"sum(`tabSales Invoice Item`.{tax_type}_amount) AS {tax_type}_amount"
        for tax_type in GST_TAX_TYPES
    )


def get_items(filters):
    fields = get_tax_fields()
    conditions = get_conditions(filters)
    match_conditions = frappe.build_match_conditions("Sales Invoice")
    if match_conditions:
        conditions += f" and {match_conditions} "

    items = frappe.db.sql(
        f"""
        SELECT
            {fields},
            COALESCE(`tabSales Invoice Item`.gst_hsn_code, '') AS gst_hsn_code,
            `tabSales Invoice Item`.uom as uqc,
            sum(`tabSales Invoice Item`.qty) AS qty,
            sum(`tabSales Invoice Item`.taxable_value) AS taxable_value,
            `tabSales Invoice Item`.parent,
            `tabSales Invoice Item`.item_code,
            `tabSales Invoice Item`.item_name,
            COALESCE(`tabGST HSN Code`.description, 'NA') AS description,
            (
                `tabSales Invoice Item`.igst_rate +
                `tabSales Invoice Item`.cgst_rate +
                `tabSales Invoice Item`.sgst_rate
            ) AS tax_rate
        FROM
            `tabSales Invoice`
            INNER JOIN `tabSales Invoice Item` ON `tabSales Invoice`.name = `tabSales Invoice Item`.parent
            LEFT JOIN `tabGST HSN Code` ON `tabSales Invoice Item`.gst_hsn_code = `tabGST HSN Code`.name
        WHERE
            `tabSales Invoice`.docstatus = 1
            AND `tabSales Invoice`.is_opening != 'Yes'
            AND `tabSales Invoice`.company_gstin != IFNULL(`tabSales Invoice`.billing_address_gstin, '') {conditions}

        GROUP BY
            `tabSales Invoice Item`.parent,
            `tabSales Invoice Item`.item_code,
            `tabSales Invoice Item`.uom
        """,
        filters,
        as_dict=1,
    )

    return items


def get_merged_data(columns, data):
    merged_hsn_dict = {}

    for row in data:
        key = f"{row['gst_hsn_code']}-{row['uqc']}-{row['tax_rate']}"
        merged_hsn_dict.setdefault(key, {})
        for d in columns:
            fieldname = d["fieldname"]
            if d["fieldtype"] not in ("Int", "Float", "Currency"):
                merged_hsn_dict[key][fieldname] = row[fieldname]
            else:
                merged_hsn_dict[key][fieldname] = (
                    merged_hsn_dict.get(key, {}).get(fieldname, 0) + row[fieldname]
                )

    return list(merged_hsn_dict.values())


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

    gst_json["hsn"] = get_hsn_wise_json_data(filters, report_data)

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


def get_hsn_wise_json_data(filters, report_data):
    filters = frappe._dict(filters)
    data = []
    count = 1

    for hsn in report_data:
        if hsn.get("gst_hsn_code") == "Total":
            continue
        row = {
            "num": count,
            "hsn_sc": hsn.get("gst_hsn_code"),
            "uqc": hsn.get("uqc"),
            "qty": flt(hsn.get("qty"), 2),
            "rt": flt(hsn.get("tax_rate"), 2),
            "txval": flt(hsn.get("taxable_amount"), 2),
            "iamt": 0.0,
            "camt": 0.0,
            "samt": 0.0,
            "csamt": 0.0,
        }

        if hsn_description := hsn.get("description"):
            row["desc"] = hsn_description[:30]

        row["iamt"] += flt(hsn.get("igst_account"), 2)
        row["camt"] += flt(hsn.get("cgst_account"), 2)
        row["samt"] += flt(hsn.get("sgst_account"), 2)
        row["csamt"] += flt(hsn.get("cess_account"), 2)

        data.append(row)
        count += 1

    return {"data": data}
