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

    data = get_document_summary(filters)

    return data


def get_document_summary(filters):
    doctype = frappe.qb.DocType("Sales Invoice")

    query = (
        frappe.qb.from_(doctype)
        .select(
            doctype.name,
            doctype.naming_series,
            doctype.creation,
            doctype.docstatus,
            doctype.is_return,
            doctype.is_debit_note,
            doctype.amended_from,
        )
        .where(doctype.company == filters.company)
        .where(doctype.posting_date.between(filters.from_date, filters.to_date))
        .where(doctype.naming_series.isnotnull())
        .orderby(doctype.name)
    )

    data = query.run(as_dict=True)

    data = filter_amended_docs(data, filters)

    summarized_data = []

    for nature_of_document, seperated_data in seperate_data_by_nature_of_document(
        data
    ).items():
        summarized_data.extend(get_summarized_data(seperated_data, nature_of_document))

    return summarized_data


def get_summarized_data(data, nature_of_document):
    if not data:
        return []

    slice_indices = []
    summarized_data = []

    for i in range(1, len(data)):
        alphabet_pattern = re.compile(r"[A-Za-z]+")
        number_pattern = re.compile(r"\d+")

        a_0 = "".join(alphabet_pattern.findall(data[i - 1].name))
        n_0 = "".join(number_pattern.findall(data[i - 1].name))

        a_1 = "".join(alphabet_pattern.findall(data[i].name))
        n_1 = "".join(number_pattern.findall(data[i].name))

        if a_1 != a_0:
            slice_indices.append(i)
            continue

        if cint(n_1) - cint(n_0) != 1:
            slice_indices.append(i)

    list_sorted_items = [
        data[i:j] for i, j in zip([0] + slice_indices, slice_indices + [None])
    ]

    for sorted_items in list_sorted_items:
        draft_count = sum(1 for item in sorted_items if item.docstatus == 0)
        total_submitted_count = sum(1 for item in sorted_items if item.docstatus == 1)
        canceled_count = sum(1 for item in sorted_items if item.docstatus == 2)

        summarized_data.append(
            {
                "naming_series": "".join(sorted_items[0].naming_series.split(".")),
                "nature_of_document": nature_of_document,
                "from_serial_no": sorted_items[0].name,
                "to_serial_no": sorted_items[-1].name,
                "total_number": total_submitted_count,
                "canceled": canceled_count,
                "total_draft": draft_count,
                "total_issued": draft_count + total_submitted_count + canceled_count,
            }
        )

    return summarized_data


def seperate_data_by_nature_of_document(data):
    nature_of_document = {
        "Invoices for outward supply": [],
        "Debit Note": [],
        "Credit Note": [],
    }

    for item in data:
        if item.is_return:
            nature_of_document["Credit Note"].append(item)
        elif item.is_debit_note:
            nature_of_document["Debit Note"].append(item)
        else:
            nature_of_document["Invoices for outward supply"].append(item)

    return nature_of_document


def filter_amended_docs(data, filters):
    data_dict = {item.name: item for item in data}
    amended_dict = {}
    amended_list = []

    for item in data:
        if (
            item.amended_from
            and len(item.amended_from) != len(item.name)
            or item.amended_from in amended_dict
        ):
            amended_dict[item.name] = item.amended_from
            amended_list.append(item.name)

    amended_list.reverse()

    for item in amended_list:
        data_dict[amended_dict[item]] = data_dict[item]
        data_dict[amended_dict[item]]["name"] = amended_dict[item]
        data_dict.pop(item)

    return list(data_dict.values())
