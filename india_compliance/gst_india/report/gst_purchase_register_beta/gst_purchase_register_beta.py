# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt
from pypika import Order

import frappe
from frappe import _
from frappe.query_builder.functions import IfNull

SECTION_MAPPING = {
    "Eligible ITC": {
        "ITC Available": [
            "Import Of Goods",
            "Import Of Service",
            "ITC on Reverse Charge",
            "Input Service Distributor",
            "All Other ITC",
        ],
    },
    "Values from Supplier under Registered Composition/Exempted/Nil-Rated/Non-GST Inward Supplies": {
        "Registered-Composition/Exempted/Nil-Rated": [
            "Registered-Composition/Exempted/Nil-Rated",
        ],
        "Non-GST": ["Non-GST"],
    },
}

AMOUNT_FIELDS = {
    "taxable_value": 0,
    "igst_amount": 0,
    "cgst_amount": 0,
    "sgst_amount": 0,
    "total_cess_amount": 0,
}


def execute(filters: dict | None = None):
    filters = frappe._dict(filters or {})

    if filters.get("summary_by") == "Overview":
        data = get_overview(filters, SECTION_MAPPING[filters.sub_section])
        columns = get_columns(filters)

    else:
        data = get_data(filters)
        columns = get_columns(filters)

    return columns, data


def get_data(filters):
    doc = frappe.qb.DocType("Purchase Invoice")
    doc_item = frappe.qb.DocType("Purchase Invoice Item")

    query = (
        frappe.qb.from_(doc)
        .inner_join(doc_item)
        .on(doc.name == doc_item.parent)
        .select(
            IfNull(doc_item.item_code, doc_item.item_name).as_("item_code"),
            doc_item.qty,
            doc_item.gst_hsn_code,
            doc.supplier,
            doc.name.as_("invoice_no"),
            doc.posting_date,
            doc.grand_total.as_("invoice_total"),
            doc.itc_classification,
            IfNull(doc_item.gst_treatment, "Not Defined").as_("gst_treatment"),
            (doc_item.cgst_rate + doc_item.sgst_rate + doc_item.igst_rate).as_(
                "gst_rate"
            ),
            doc_item.taxable_value,
            doc_item.cgst_amount,
            doc_item.sgst_amount,
            doc_item.igst_amount,
            doc_item.cess_amount,
            doc_item.cess_non_advol_amount,
            (doc_item.cess_amount + doc_item.cess_non_advol_amount).as_(
                "total_cess_amount"
            ),
            (
                doc_item.cgst_amount
                + doc_item.sgst_amount
                + doc_item.igst_amount
                + doc_item.cess_amount
                + doc_item.cess_non_advol_amount
            ).as_("total_tax"),
            (
                doc_item.taxable_value
                + doc_item.cgst_amount
                + doc_item.sgst_amount
                + doc_item.igst_amount
                + doc_item.cess_amount
                + doc_item.cess_non_advol_amount
            ).as_("total_amount"),
        )
        .where(doc.docstatus == 1)
        .orderby(doc.name, order=Order.desc)
    )

    if filters.get("company"):
        query = query.where(doc.company == filters.company)

    if filters.get("date_range"):
        from_date = filters.date_range[0]
        to_date = filters.date_range[1]

        query = query.where(doc.posting_date >= from_date)
        query = query.where(doc.posting_date <= to_date)

    data = query.run(as_dict=True)

    set_invoice_sub_category(data, filters.sub_section)

    if filters.get("invoice_sub_category"):
        data = [
            d for d in data if d.invoice_sub_category == filters.invoice_sub_category
        ]

    return data


def get_columns(filters):
    base_columns = [
        {
            "fieldname": "invoice_no",
            "label": _("Invoice Number"),
            "fieldtype": "Link",
            "options": "Purchase Invoice",
            "width": 180,
        },
        {
            "fieldname": "supplier",
            "label": _("Supplier"),
            "fieldtype": "Link",
            "options": "Supplier",
            "width": 200,
        },
        {
            "fieldname": "item_code",
            "label": _("Item Code"),
            "fieldtype": "Link",
            "options": "Item",
            "width": 180,
        },
        {"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 90},
        {
            "fieldname": "gst_hsn_code",
            "label": _("HSN Code"),
            "fieldtype": "Link",
            "options": "GST HSN Code",
            "width": 100,
        },
        {
            "fieldname": "posting_date",
            "label": _("Posting Date"),
            "fieldtype": "Date",
            "width": 90,
        },
        {
            "fieldname": "invoice_total",
            "label": _("Invoice Total"),
            "fieldtype": "Data",
            "width": 90,
        },
        {
            "fieldname": "gst_treatment",
            "label": _("GST Treatment"),
            "fieldtype": "Data",
            "width": 90,
        },
        {
            "fieldname": "gst_rate",
            "label": _("GST Rate"),
            "fieldtype": "Percent",
            "width": 90,
        },
        {
            "fieldname": "taxable_value",
            "label": _("Taxable Value"),
            "fieldtype": "Currency",
            "width": 90,
        },
        {
            "fieldname": "cgst_amount",
            "label": _("CGST Amount"),
            "fieldtype": "Currency",
            "width": 90,
        },
        {
            "fieldname": "sgst_amount",
            "label": _("SGST Amount"),
            "fieldtype": "Currency",
            "width": 90,
        },
        {
            "fieldname": "igst_amount",
            "label": _("IGST Amount"),
            "fieldtype": "Currency",
            "width": 90,
        },
        {
            "fieldname": "cess_amount",
            "label": _("CESS Amount"),
            "fieldtype": "Currency",
            "width": 90,
        },
        {
            "fieldname": "cess_non_advol_amount",
            "label": _("CESS Non Advol Amount"),
            "fieldtype": "Currency",
            "width": 90,
        },
        {
            "fieldname": "total_cess_amount",
            "label": _("Total CESS Amount"),
            "fieldtype": "Currency",
            "width": 90,
        },
        {
            "fieldname": "total_tax",
            "label": _("Total Tax"),
            "fieldtype": "Currency",
            "width": 90,
        },
        {
            "fieldname": "total_amount",
            "label": _("Total Amount"),
            "fieldtype": "Currency",
            "width": 90,
        },
        {
            "fieldname": "invoice_sub_category",
            "label": _("Invoice Sub Category"),
            "fieldtype": "Data",
            "width": 90,
        },
    ]

    if filters.get("summary_by") == "Overview":
        overview_columns = [
            {"label": _("Description"), "fieldname": "description", "width": "240"},
            {
                "label": _("No. of records"),
                "fieldname": "no_of_records",
                "width": "120",
                "fieldtype": "Int",
            },
            {
                "label": _("Taxable Value"),
                "fieldname": "taxable_value",
                "width": "120",
                "fieldtype": "Currency",
            },
            {
                "label": _("IGST Amount"),
                "fieldname": "igst_amount",
                "width": "120",
                "fieldtype": "Currency",
            },
            {
                "label": _("CGST Amount"),
                "fieldname": "cgst_amount",
                "width": "120",
                "fieldtype": "Currency",
            },
            {
                "label": _("SGST Amount"),
                "fieldname": "sgst_amount",
                "width": "120",
                "fieldtype": "Currency",
            },
            {
                "label": _("Total Cess Amount"),
                "fieldname": "total_cess_amount",
                "width": "120",
                "fieldtype": "Currency",
            },
        ]
        return overview_columns

    return base_columns


def get_overview(filters, mapping):
    final_summary = []
    sub_category_summary = get_sub_category_summary(filters, mapping)

    for category, sub_categories in mapping.items():
        category_summary = {
            "description": category,
            "no_of_records": 0,
            "indent": 0,
            **AMOUNT_FIELDS,
        }
        final_summary.append(category_summary)

        for sub_category in sub_categories:
            sub_category_row = sub_category_summary[sub_category]
            category_summary["no_of_records"] += sub_category_row["no_of_records"]

            for key in AMOUNT_FIELDS:
                category_summary[key] += sub_category_row[key]

            final_summary.append(sub_category_row)

    return final_summary


def get_sub_category_summary(filters, mapping):
    invoices = get_data(filters)
    sub_categories = []
    for category in mapping:
        sub_categories.extend(mapping[category])

    summary = {
        category: {
            "description": category,
            "no_of_records": 0,
            "indent": 1,
            "unique_records": set(),
            **AMOUNT_FIELDS,
        }
        for category in sub_categories
    }

    def _update_summary_row(row, sub_category_field="invoice_sub_category"):
        if row.get(sub_category_field) not in sub_categories:
            return

        summary_row = summary[row.get(sub_category_field)]

        for key in AMOUNT_FIELDS:
            summary_row[key] += row[key]

        summary_row["unique_records"].add(row.invoice_no)

    for row in invoices:
        _update_summary_row(row)

    for summary_row in summary.values():
        summary_row["no_of_records"] = len(summary_row["unique_records"])

    return summary


def set_invoice_sub_category(data, sub_section):
    if sub_section == "Eligible ITC":
        for row in data:
            row.invoice_sub_category = row.itc_classification
    else:
        for row in data:
            row.invoice_sub_category = (
                "Non-GST"
                if row.gst_treatment == "Non-GST"
                else "Registered-Composition/Exempted/Nil-Rated"
            )
