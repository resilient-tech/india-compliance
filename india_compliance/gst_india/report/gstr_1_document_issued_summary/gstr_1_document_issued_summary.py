# Copyright (c) 2022, Resilient Tech and contributors
# For license information, please see license.txt
import re

import frappe
from frappe import _
from frappe.utils import cint


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
            "label": _("Submitted Number"),
            "fieldtype": "Int",
            "width": 180,
        },
        {
            "fieldname": "total_draft",
            "label": _("Draft Number"),
            "fieldtype": "Int",
            "width": 150,
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
        "Debit Note": "Sales Invoice",
        "Credit Note": "Sales Invoice",
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
        .orderby(doctype.creation)
    )

    query = apply_document_wise_condition(filters, query, nature_of_document, doctype)

    data = query.run(as_dict=True)

    return get_summarized_data(data, nature_of_document)


def get_summarized_data(data, nature_of_document):
    naming_series_data = {}

    for item in data:
        naming_series, item.serial_number = _parse_naming_series(doc=item)
        naming_series_data.setdefault(naming_series, {})
        naming_series_data[naming_series][item.serial_number] = item

    summarized_data = []

    for naming_series, items in naming_series_data.items():
        if not items:
            continue

        sorted_items = sorted(items.items(), key=lambda x: x[0])

        slice_indices = [
            i
            for i in range(1, len(sorted_items))
            if sorted_items[i][0] - sorted_items[i - 1][0] != 1
        ]

        list_sorted_items = [
            sorted_items[i:j]
            for i, j in zip([0] + slice_indices, slice_indices + [None])
        ]

        for sorted_items in list_sorted_items:
            draft_count = sum(1 for item in sorted_items if item[1].docstatus == 0)
            total_submitted_count = sum(
                1 for item in sorted_items if item[1].docstatus == 1
            )
            canceled_count = sum(1 for item in sorted_items if item[1].docstatus == 2)

            summarized_data.append(
                {
                    "naming_series": naming_series,
                    "nature_of_document": nature_of_document,
                    "from_serial_no": sorted_items[0][1].name,
                    "to_serial_no": sorted_items[-1][1].name,
                    "total_number": total_submitted_count,
                    "canceled": canceled_count,
                    "total_draft": draft_count,
                    "total_issued": draft_count
                    + total_submitted_count
                    + canceled_count,
                }
            )

    return summarized_data


def apply_document_wise_condition(filters, query, nature_of_document, doctype):
    if filters.get("company_gstin"):
        query = query.where(doctype.company_gstin == filters.company_gstin)

    if nature_of_document == "Invoices for outward supply":
        query = query.where(doctype.is_return == 0)
        query = query.where(doctype.is_debit_note == 0)
    elif nature_of_document == "Debit Note":
        query = query.where(doctype.is_debit_note == 1)
    elif nature_of_document == "Credit Note":
        query = query.where(doctype.is_return == 1)

    return query


def _parse_naming_series(doc):
    naming_series = doc.naming_series.replace(".", "")
    hash = re.search("#+", naming_series)

    if not hash:
        naming_series += "#####"
        hash = re.search("#+", naming_series)

    serial_number = cint(doc.name[hash.start() : hash.end()])

    new_naming_series = doc.name.replace(
        doc.name[hash.start() : hash.end()], hash.group()
    )

    # Remove suffix from amended documents having names like SINV-23-00001-1
    if len(new_naming_series) > len(naming_series):
        new_naming_series = new_naming_series[: len(naming_series)]

    return (
        new_naming_series,
        serial_number,
    )
