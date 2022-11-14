# Copyright (c) 2022, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.naming import parse_naming_series


def execute(filters=None):
    columns = get_columns(filters)
    data = get_data(filters)

    return columns, data


def get_columns(filters) -> list:
    return [
        {
            "fieldname": "nature_of_document",
            "label": _("Nature of Document"),
            "fieldtype": "Data",
            "width": 300,
        },
        {
            "fieldname": "naming_series",
            "label": _("Series"),
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "fieldname": "from_serial_no",
            "label": _("Serial Number From"),
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "fieldname": "to_serial_no",
            "label": _("Serial Number To"),
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "fieldname": "total_number",
            "label": _("Total Submitted Number"),
            "fieldtype": "Int",
            "width": 180,
        },
        {
            "fieldname": "canceled",
            "label": _("Canceled Number"),
            "fieldtype": "Int",
            "width": 160,
        },
        {
            "fieldname": "total_issued",
            "label": _("Total Issued Documents"),
            "fieldtype": "Int",
            "width": 150,
        },
    ]


def get_data(filters) -> list:
    data = []

    document_mapper = {
        "Invoices for outward supply": "Sales Invoice",
        "Invoices for inward supply": "Purchase Invoice",
        "Invoices for inward supply from unregistered person": "Purchase Invoice",
        "Debit Note": "Purchase Invoice",
        "Credit Note": "Sales Invoice",
        "Receipt Voucher": "Payment Entry",
        "Payment Voucher": "Payment Entry",
        "Receipt Voucher (JV)": "Journal Entry",
        "Payment Voucher (JV)": "Journal Entry",
    }

    for nature_of_document, document_type in document_mapper.items():
        data.extend(get_document_summary(filters, document_type, nature_of_document))

    return data


def get_document_summary(filters, document_type, nature_of_document):
    doctype = frappe.qb.DocType(document_type)

    query = (
        frappe.qb.from_(doctype)
        .select(
            doctype.name, doctype.naming_series, doctype.creation, doctype.docstatus
        )
        .where(doctype.company == filters.company)
        .where(doctype.posting_date.between(filters.from_date, filters.to_date))
        .where(doctype.naming_series.isnotnull())
        .where(doctype.docstatus > 0)
    )

    query = apply_document_wise_condition(filters, query, nature_of_document, doctype)

    data = query.run(as_dict=True)

    naming_series_data = {}

    for item in data:
        naming_series = parse_naming_series(
            item.naming_series.replace("#", ""), doc=item
        )

        naming_series_data.setdefault(
            naming_series, {"canceled_count": 0, "total_count": 0, "document_names": {}}
        )

        names = naming_series_data.get(naming_series)
        if item.docstatus == 2:
            names["canceled_count"] += 1

        names["document_names"][item.name] = item.creation
        names["total_count"] += 1

    res = []
    for naming_series, name_data in naming_series_data.items():
        if not name_data:
            continue

        sorted_names = sorted(name_data["document_names"].items(), key=lambda x: x[1])
        if sorted_names and len(sorted_names[0]) > 0:
            res.append(
                frappe._dict(
                    {
                        "naming_series": naming_series,
                        "nature_of_document": nature_of_document,
                        "from_serial_no": sorted_names[0][0],
                        "to_serial_no": sorted_names[len(sorted_names) - 1][0],
                        "total_number": name_data.get("total_count"),
                        "canceled": name_data.get("canceled_count"),
                        "total_issued": name_data.get("canceled_count")
                        + name_data.get("total_count"),
                    }
                )
            )

    return res


def apply_document_wise_condition(filters, query, nature_of_document, doctype):
    if doctype == "Purchase Invoice" and filters.get("company_address"):
        query = query.where(doctype.shipping_address == filters.company_address)
    elif filters.get("company_gstin"):
        query = query.where(doctype.company_gstin == filters.company_gstin)

    bank_accounts = get_bank_accounts(filters.company)

    if nature_of_document == "Invoices for outward supply":
        query = query
    elif nature_of_document == "Invoices for inward supply":
        query = query.where(doctype.gst_category != "Unregistered")
    elif nature_of_document == "Invoices for inward supply from unregistered person":
        query = query.where(doctype.gst_category == "Unregistered")
    elif nature_of_document == "Debit Note":
        query = query.where(doctype.is_return == 1)
    elif nature_of_document == "Credit Note":
        query = query.where(doctype.is_return == 1)
    elif nature_of_document == "Receipt Voucher":
        query = query.where(doctype.payment_type == "Receive")
    elif nature_of_document == "Payment Voucher":
        query = query.where(doctype.payment_type == "Pay")
    elif nature_of_document == "Receipt Voucher (JV)":
        journal_entries = frappe.db.get_all(
            "Journal Entry Account",
            filters={"account": ("in", bank_accounts), "debit": (">", 0), "credit": 0},
            pluck="parent",
        )
        query = query.where(doctype.name.isin(journal_entries)).where(
            doctype.voucher_type != "Contra Entry"
        )
    elif nature_of_document == "Payment Voucher (JV)":
        journal_entries = frappe.db.get_all(
            "Journal Entry Account",
            filters={"account": ("in", bank_accounts), "debit": (">", 0), "credit": 0},
            pluck="parent",
        )
        query = query.where(doctype.name.isin(journal_entries)).where(
            doctype.voucher_type != "Contra Entry"
        )

    return query


def get_bank_accounts(company):
    bank_accounts = frappe.db.get_all(
        "Account",
        {"company": company, "account_type": "Bank", "is_group": 0},
        pluck="name",
    )

    return bank_accounts
