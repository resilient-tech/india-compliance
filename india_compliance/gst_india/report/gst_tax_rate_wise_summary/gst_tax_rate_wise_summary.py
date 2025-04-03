# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _

AMOUNT_FIELDS = (
    "taxable_value",
    "cgst_amount",
    "sgst_amount",
    "igst_amount",
    "cess_amount",
)


def execute(filters: dict | None = None):
    filters = frappe._dict(filters or {})
    filters.from_date, filters.to_date = filters.date_range

    columns = get_columns(filters)
    data = get_data(filters)
    data = process_data(data)

    return columns, data


def get_columns(filters):
    company_currency = frappe.get_cached_value(
        "Company", filters.get("company"), "default_currency"
    )

    return [
        {
            "label": _("Description"),
            "fieldname": "description",
            "fieldtype": "Data",
            "width": 250,
        },
        {
            "fieldname": "taxable_value",
            "label": _("Taxable Value"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 170,
        },
        {
            "fieldname": "cgst_amount",
            "label": _("CGST Amount"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 170,
        },
        {
            "fieldname": "sgst_amount",
            "label": _("SGST Amount"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 170,
        },
        {
            "fieldname": "igst_amount",
            "label": _("IGST Amount"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 170,
        },
        {
            "fieldname": "cess_amount",
            "label": _("CESS Amount"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 170,
        },
    ]


def get_data(filters):
    doctype = (
        "Sales Invoice"
        if filters.voucher_type == "Sales Invoice"
        else "Purchase Invoice"
    )

    doc = frappe.qb.DocType(doctype)
    doc_item = frappe.qb.DocType(f"{doctype} Item")

    query = (
        frappe.qb.from_(doc)
        .join(doc_item)
        .on(doc.name == doc_item.parent)
        .select(
            doc_item.taxable_value.as_("taxable_value"),
            doc_item.cgst_amount.as_("cgst_amount"),
            doc_item.sgst_amount.as_("sgst_amount"),
            doc_item.igst_amount.as_("igst_amount"),
            (doc_item.cess_amount + doc_item.cess_non_advol_amount).as_("cess_amount"),
            doc_item.gst_treatment.as_("gst_treatment"),
            (doc_item.igst_rate + doc_item.cgst_rate + doc_item.sgst_rate).as_(
                "tax_rate"
            ),
        )
        .where(
            (doc.docstatus == 1)
            & (doc.posting_date[filters.from_date : filters.to_date])
            & (doc.company == filters.company)
            & (doc.company_gstin == filters.company_gstin)
        )
    )

    if filters.voucher_type == "Purchase Reverse Charge":
        query = query.where(doc.is_reverse_charge == 1)

    return query.run(as_dict=True)


def process_data(data):
    invoice_wise_data = {}

    for invoice in data:
        # Determine the key field
        key_field = (
            "tax_rate" if invoice.gst_treatment == "Taxable" else "gst_treatment"
        )
        key_value = f"{invoice.get(key_field)}"

        if key_value not in invoice_wise_data:
            invoice_wise_data[key_value] = invoice
        else:
            for field in AMOUNT_FIELDS:
                invoice_wise_data[key_value][field] += invoice[field]

        # Set description based on key field
        if key_field == "tax_rate":
            invoice_wise_data[key_value].description = f"{key_value} %"
        else:
            invoice_wise_data[key_value].description = key_value

    return list(invoice_wise_data.values())
