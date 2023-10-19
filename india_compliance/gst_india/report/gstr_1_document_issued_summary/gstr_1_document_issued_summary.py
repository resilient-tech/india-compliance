# Copyright (c) 2022, Resilient Tech and contributors
# For license information, please see license.txt
import re

import frappe
from frappe import _
from frappe.model.naming import parse_naming_series
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

    return get_processed_data(data, nature_of_document)


def get_processed_data(data, nature_of_document):
    naming_series_data = {}

    # Group items by naming series and serial number
    for item in data:
        naming_series = parse_naming_series(
            item.naming_series.replace("#", ""), doc=item
        )
        item.serial_number = get_serial_number(item)
        naming_series_data.setdefault(naming_series, {})
        naming_series_data[naming_series][item.serial_number] = item

    processed_data = []

    # Process items for each naming series
    for naming_series, items in naming_series_data.items():
        if not items:
            continue

        # Sort items by serial number
        sorted_items = sorted(items.items(), key=lambda x: x[0])

        # Split items into contiguous groups
        slice_indices = [
            i
            for i in range(1, len(sorted_items))
            if sorted_items[i][0] - sorted_items[i - 1][0] != 1
        ]
        list_sorted_items = [
            sorted_items[i:j]
            for i, j in zip([0] + slice_indices, slice_indices + [None])
        ]

        # Process items in each group
        for sorted_items in list_sorted_items:
            draft_count = sum(1 for item in sorted_items if item[1].docstatus == 0)
            total_submitted_count = sum(
                1 for item in sorted_items if item[1].docstatus == 1
            )
            canceled_count = sum(1 for item in sorted_items if item[1].docstatus == 2)

            processed_data.append(
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

    return processed_data


def get_serial_number(item):
    if ".#" in item.naming_series:
        prefix, hashes = item.naming_series.rsplit(".", 1)
        if "#" not in hashes:
            hash = re.search("#+", item.naming_series)
            if not hash:
                return
            item.name = item.name.replace(hashes, "")
            prefix = prefix.replace(hash.group(), "")
    else:
        prefix = item.naming_series

    if "." in prefix:
        prefix = parse_naming_series(prefix.split("."), doc=item)

    count = item.name.replace(prefix, "")

    if "-" in count:
        count = count.split("-")[0]

    return cint(count)


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


def get_bank_accounts(company):
    bank_accounts = frappe.db.get_all(
        "Account",
        {"company": company, "account_type": "Bank", "is_group": 0},
        pluck="name",
    )

    return bank_accounts
