# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt
import frappe
from frappe import _

from india_compliance.gst_india.utils.gstr3b.gstr3b_data import GSTR3BInvoices

SECTION_MAPPING = {
    "4": {
        "ITC Available": [
            "Import Of Goods",
            "Import Of Service",
            "ITC on Reverse Charge",
            "Input Service Distributor",
            "All Other ITC",
        ],
        "ITC Reversed": [
            "As per rules 42 & 43 of CGST Rules and section 17(5)",
            "Others",
        ],
        "Ineligible ITC": [
            "Reclaim of ITC Reversal",
            "ITC restricted due to PoS rules",
        ],
    },
    "5": {
        "Composition Scheme, Exempted, Nil Rated": [
            "Composition Scheme, Exempted, Nil Rated",
        ],
        "Non-GST": ["Non-GST"],
    },
}


AMOUNT_FIELDS_MAP = {
    "4": {
        "igst_amount": 0,
        "cgst_amount": 0,
        "sgst_amount": 0,
        "cess_amount": 0,
    },
    "5": {
        "intra": 0,
        "inter": 0,
    },
}


def execute(filters: dict | None = None):
    filters.from_date, filters.to_date = filters.get("date_range")

    data = get_data(filters)
    columns = get_columns(filters)

    return columns, data


def get_columns(filters):
    columns = initialize_columns(filters)

    if filters.summary_by == "Summary by Item":
        columns.extend(get_item_wise_columns())
    elif filters.summary_by == "Overview":
        columns.extend(get_summary_columns(filters))
    else:
        columns.extend(get_invoice_wise_columns())

    columns.extend(
        [
            {
                "fieldname": "invoice_type",
                "label": _("Invoice Type"),
                "fieldtype": "Data",
                "width": 200,
                "hidden": filters.summary_by == "Overview"
                or filters.sub_section != "5",
            },
            {
                "fieldname": "invoice_sub_category",
                "label": _("Invoice Sub Category"),
                "fieldtype": "Data",
                "width": 200,
                "hidden": filters.summary_by == "Overview",
            },
        ]
    )

    return columns


def initialize_columns(filters):
    if filters.summary_by == "Overview":
        return [
            {
                "label": _("Description"),
                "fieldname": "description",
                "width": "400",
            },
            {
                "label": _("No. of records"),
                "fieldname": "no_of_records",
                "width": "120",
                "fieldtype": "Int",
            },
        ]
    else:
        return [
            {
                "fieldname": "voucher_type",
                "label": _("Voucher Type"),
                "fieldtype": "Data",
                "width": 200,
            },
            {
                "fieldname": "voucher_no",
                "label": _("Voucher No"),
                "fieldtype": "Dynamic Link",
                "options": "voucher_type",
                "width": 200,
            },
            {
                "fieldname": "posting_date",
                "label": _("Posting Date"),
                "fieldtype": "Date",
                "width": 150,
            },
        ]


def get_item_wise_columns():
    return [
        {
            "fieldname": "item_code",
            "label": _("Item Code"),
            "fieldtype": "Link",
            "options": "Item",
            "width": 180,
        },
        {
            "fieldname": "qty",
            "label": _("Item Qty"),
            "fieldtype": "Data",
            "width": 90,
        },
        {
            "fieldname": "gst_hsn_code",
            "label": _("HSN Code"),
            "fieldtype": "Link",
            "options": "GST HSN Code",
            "width": 120,
        },
        {
            "fieldname": "uom",
            "label": _("UOM"),
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "fieldname": "gst_rate",
            "label": _("GST Rate"),
            "fieldtype": "Percent",
            "width": 90,
        },
        *get_tax_columns(),
    ]


def get_summary_columns(filters):
    company_currency = frappe.get_cached_value(
        "Company", filters.get("company"), "default_currency"
    )

    if filters.sub_section == "4":
        return [
            {
                "fieldname": "igst_amount",
                "label": _("Integrated Tax"),
                "fieldtype": "Currency",
                "options": company_currency,
                "width": 120,
            },
            {
                "fieldname": "cgst_amount",
                "label": _("Central Tax"),
                "fieldtype": "Currency",
                "options": company_currency,
                "width": 120,
            },
            {
                "fieldname": "sgst_amount",
                "label": _("State/UT Tax"),
                "fieldtype": "Currency",
                "options": company_currency,
                "width": 120,
            },
            {
                "fieldname": "cess_amount",
                "label": _("Cess Tax"),
                "fieldtype": "Currency",
                "options": company_currency,
                "width": 120,
            },
        ]

    else:
        return [
            {
                "fieldname": "inter",
                "label": _("Inter State"),
                "fieldtype": "Currency",
                "options": company_currency,
                "width": 120,
            },
            {
                "fieldname": "intra",
                "label": _("Intra State"),
                "fieldtype": "Currency",
                "options": company_currency,
                "width": 120,
            },
        ]


def get_invoice_wise_columns():
    return [
        {
            "fieldname": "gst_category",
            "label": _("GST Category"),
            "fieldtype": "Data",
            "width": 150,
        },
        *get_tax_columns(),
    ]


def get_tax_columns():
    return [
        {
            "fieldname": "taxable_value",
            "label": _("Taxable Value"),
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "cgst_amount",
            "label": _("CGST Amount"),
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "sgst_amount",
            "label": _("SGST Amount"),
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "igst_amount",
            "label": _("IGST Amount"),
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "cess_amount",
            "label": _("CESS Amount"),
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "total_tax",
            "label": _("Total Tax"),
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "total_amount",
            "label": _("Total Amount"),
            "fieldtype": "Currency",
            "width": 150,
        },
    ]


def get_data(filters):
    data = []
    gstr3b_invoices = GSTR3BInvoices(filters)
    is_grouped_by_invoice = filters.summary_by != "Summary by Item"
    sub_section = filters.sub_section

    doctypes = ["Purchase Invoice"]
    if sub_section == "4":
        doctypes.extend(["Bill of Entry", "Journal Entry"])

    for doctype in doctypes:
        data.extend(gstr3b_invoices.get_data(doctype, is_grouped_by_invoice))

    if filters.summary_by == "Overview":
        return get_summary_view(data, sub_section)

    data = sorted(
        gstr3b_invoices.get_filtered_invoices(data, filters.invoice_sub_category),
        key=lambda k: (k["invoice_sub_category"], k["posting_date"]),
    )

    return data


def get_summary_view(data, sub_section):
    mapping = SECTION_MAPPING[sub_section]
    amount_fields = AMOUNT_FIELDS_MAP[sub_section]

    final_summary = []
    sub_category_summary = get_sub_category_summary(data, mapping, amount_fields)

    for category, sub_categories in mapping.items():
        if category == "Ineligible ITC" and sub_section == "4":
            add_net_itc_row(final_summary, amount_fields)

        category_summary = {
            "description": category,
            "no_of_records": 0,
            "indent": 0,
            **amount_fields,
        }
        final_summary.append(category_summary)

        for sub_category in sub_categories:
            sub_category_row = sub_category_summary[sub_category]
            category_summary["no_of_records"] += sub_category_row["no_of_records"]

            for key in amount_fields:
                category_summary[key] += sub_category_row[key]

            final_summary.append(sub_category_row)

    return final_summary


def add_net_itc_row(summary, amount_fields):
    row = {
        "description": "Net ITC Available",
        "no_of_records": 0,
        "indent": 0,
        **amount_fields,
    }

    for summary_row in summary:
        if summary_row["description"] == "ITC Available":
            for key in amount_fields:
                row[key] += summary_row[key]
            row["no_of_records"] += summary_row["no_of_records"]

        elif summary_row["description"] == "ITC Reversed":
            for key in amount_fields:
                row[key] -= summary_row[key]
            row["no_of_records"] -= summary_row["no_of_records"]

    summary.append(row)


def get_sub_category_summary(data, mapping, amount_fields):
    sub_categories = []
    for category in mapping:
        sub_categories.extend(mapping[category])

    summary = {
        category: {
            "description": category,
            "no_of_records": 0,
            "indent": 1,
            "unique_records": set(),
            **amount_fields,
        }
        for category in sub_categories
    }

    def _update_summary_row(row):
        if row.get("invoice_sub_category") not in sub_categories:
            return

        summary_row = summary[row.get("invoice_sub_category")]

        for key in amount_fields:
            summary_row[key] += row[key]

        summary_row["unique_records"].add(row["voucher_no"])

    for row in data:
        _update_summary_row(row)

    for summary_row in summary.values():
        summary_row["no_of_records"] = len(summary_row["unique_records"])

    return summary
