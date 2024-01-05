# Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import json

import frappe
from frappe import _
from frappe.model.meta import get_field_precision
from frappe.utils import cstr, flt, getdate
import erpnext

from india_compliance.gst_india.constants import GST_ACCOUNT_FIELDS
from india_compliance.gst_india.utils import get_gst_accounts_by_type, get_gst_uom


def execute(filters=None):
    if not filters:
        filters = {}

    validate_filters(filters)

    columns = get_columns()
    output_gst_accounts_dict = get_gst_accounts_by_type(filters.company, "Output")

    data = get_hsn_data(filters, columns, output_gst_accounts_dict)

    return columns, data


def get_hsn_data(filters, columns, output_gst_accounts_dict):
    output_gst_accounts = set()
    non_cess_accounts = set()
    for account_type, account_name in output_gst_accounts_dict.items():
        if not account_name:
            continue

        output_gst_accounts.add(account_name)
        if account_type in GST_ACCOUNT_FIELDS[:3]:
            non_cess_accounts.add(account_name)

    company_currency = erpnext.get_company_currency(filters.company)
    item_list = get_items(filters)
    itemised_tax, tax_columns = get_tax_accounts(
        item_list, columns, company_currency, output_gst_accounts
    )

    data = []
    added_item = set()

    for d in item_list:
        key = (d.parent, d.gst_hsn_code, d.item_code)
        if key in added_item:
            continue

        if d.gst_hsn_code.startswith("99"):
            # service item doesn't have qty/uom
            d.stock_qty = 0
            d.uqc = "NA"
        else:
            d.uqc = get_gst_uom(d.get("uqc"))

        total_tax = 0
        tax_rate = 0

        item_tax = itemised_tax.get((d.parent, d.item_code), {})
        for tax in tax_columns:
            tax_data = item_tax.get(tax, {})
            total_tax += flt(tax_data.get("tax_amount", 0))
            if tax in non_cess_accounts:
                tax_rate += flt(tax_data.get("tax_rate", 0))

        row = [
            d.gst_hsn_code,
            d.description,
            d.uqc,
            d.stock_qty,
            tax_rate,
            d.taxable_value + total_tax,
            d.taxable_value,
        ]

        for tax in tax_columns:
            row.append(item_tax.get(tax, {}).get("tax_amount", 0))

        data.append(row)
        added_item.add(key)

    if data:
        data = get_merged_data(columns, data)  # merge same hsn code data

    return data


def validate_filters(filters):
    from_date, to_date = filters.get("from_date"), filters.get("to_date")

    if from_date and to_date and getdate(to_date) < getdate(from_date):
        frappe.throw(_("To Date cannot be less than From Date"))


def get_columns():
    columns = [
        {
            "fieldname": "gst_hsn_code",
            "label": _("HSN/SAC"),
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
            "fieldname": "stock_qty",
            "label": _("Stock Qty"),
            "fieldtype": "Float",
            "width": 90,
        },
        {
            "fieldname": "tax_rate",
            "label": _("Tax Rate"),
            "fieldtype": "Data",
            "width": 90,
        },
        {
            "fieldname": "total_amount",
            "label": _("Total Amount"),
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "width": 120,
        },
        {
            "fieldname": "taxable_amount",
            "label": _("Total Taxable Amount"),
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
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


def get_items(filters):
    conditions = get_conditions(filters)
    match_conditions = frappe.build_match_conditions("Sales Invoice")
    if match_conditions:
        conditions += f" and {match_conditions} "

    items = frappe.db.sql(
        f"""
        SELECT
            `tabSales Invoice Item`.gst_hsn_code,
            `tabSales Invoice Item`.stock_uom as uqc,
            sum(`tabSales Invoice Item`.stock_qty) AS stock_qty,
            sum(`tabSales Invoice Item`.taxable_value) AS taxable_value,
            `tabSales Invoice Item`.parent,
            `tabSales Invoice Item`.item_code,
            COALESCE(`tabGST HSN Code`.description, 'NA') AS description
        FROM
            `tabSales Invoice`
            INNER JOIN `tabSales Invoice Item` ON `tabSales Invoice`.name = `tabSales Invoice Item`.parent
            LEFT JOIN `tabGST HSN Code` ON `tabSales Invoice Item`.gst_hsn_code = `tabGST HSN Code`.name
        WHERE
            `tabSales Invoice`.docstatus = 1
            AND `tabSales Invoice`.company_gstin != IFNULL(`tabSales Invoice`.billing_address_gstin, '')
            AND `tabSales Invoice Item`.gst_hsn_code IS NOT NULL {conditions}
        GROUP BY
            `tabSales Invoice Item`.parent,
            `tabSales Invoice Item`.item_code
        """,
        filters,
        as_dict=1,
    )

    return items


def get_tax_accounts(
    item_list,
    columns,
    company_currency,
    output_gst_accounts,
):
    if not item_list:
        return [], {}

    tax_doctype = "Sales Taxes and Charges"
    tax_columns = set()
    itemised_tax = {}

    tax_amount_precision = (
        get_field_precision(
            frappe.get_meta(tax_doctype).get_field("tax_amount"),
            currency=company_currency,
        )
        or 2
    )

    invoice_numbers = [d.parent for d in item_list]

    doctype = frappe.qb.DocType(tax_doctype)

    tax_details = (
        frappe.qb.from_(doctype)
        .select(
            doctype.parent,
            doctype.account_head,
            doctype.item_wise_tax_detail,
            doctype.base_tax_amount_after_discount_amount,
        )
        .where(doctype.parenttype == "Sales Invoice")
        .where(doctype.docstatus == 1)
        .where(doctype.parent.isin(invoice_numbers))
        .where(doctype.account_head.isin(output_gst_accounts))
    ).run()

    for parent, account_head, item_wise_tax_detail, tax_amount in tax_details:
        if not item_wise_tax_detail:
            continue

        if account_head and tax_amount:
            # as description is text editor earlier and markup can break the column convention in reports
            tax_columns.add(account_head)

        try:
            item_taxes = json.loads(item_wise_tax_detail)
            for item_code, tax_data in item_taxes.items():
                tax_rate, tax_amount = tax_data
                if not tax_amount:
                    continue

                item_taxes = itemised_tax.setdefault((parent, item_code), {})
                item_taxes[account_head] = frappe._dict(
                    tax_rate=flt(tax_rate, 2),
                    tax_amount=flt(tax_amount, tax_amount_precision),
                )

        except ValueError:
            continue

    for account_head in tax_columns:
        if account_head not in output_gst_accounts:
            continue

        columns.append(
            {
                "label": account_head,
                "fieldname": frappe.scrub(account_head),
                "fieldtype": "Float",
                "width": 110,
            }
        )

    return itemised_tax, tax_columns


def get_merged_data(columns, data):
    merged_hsn_dict = {}

    for row in data:
        key = f"{row[0]}-{row[2]}-{row[4]}"
        merged_hsn_dict.setdefault(key, {})
        for i, d in enumerate(columns):
            fieldname = d["fieldname"]
            if d["fieldtype"] not in ("Int", "Float", "Currency"):
                merged_hsn_dict[key][fieldname] = row[i]
            else:
                merged_hsn_dict[key][fieldname] = (
                    merged_hsn_dict.get(key, {}).get(fieldname, 0) + row[i]
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
    gst_accounts = get_gst_accounts_by_type(filters.company, "Output")
    data = []
    count = 1

    for hsn in report_data:
        if hsn.get("gst_hsn_code") == "Total":
            continue
        row = {
            "num": count,
            "hsn_sc": hsn.get("gst_hsn_code"),
            "uqc": hsn.get("uqc"),
            "qty": flt(hsn.get("stock_qty"), 2),
            "rt": flt(hsn.get("tax_rate"), 2),
            "txval": flt(hsn.get("taxable_amount"), 2),
            "iamt": 0.0,
            "camt": 0.0,
            "samt": 0.0,
            "csamt": 0.0,
        }

        if hsn_description := hsn.get("description"):
            row["desc"] = hsn_description[:30]

        row["iamt"] += flt(
            hsn.get(frappe.scrub(cstr(gst_accounts.get("igst_account"))), 0.0), 2
        )

        row["camt"] += flt(
            hsn.get(frappe.scrub(cstr(gst_accounts.get("cgst_account"))), 0.0), 2
        )

        row["samt"] += flt(
            hsn.get(frappe.scrub(cstr(gst_accounts.get("sgst_account"))), 0.0), 2
        )

        row["csamt"] += flt(
            hsn.get(frappe.scrub(cstr(gst_accounts.get("cess_account"))), 0.0), 2
        )

        data.append(row)
        count += 1

    return {"data": data}
