# Copyright (c) 2022, Resilient Tech and contributors
# For license information, please see license.txt
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Optional

import frappe
from frappe import _
from frappe.model.naming import (
    NAMING_SERIES_PART_TYPES,
    determine_consecutive_week_number,
    getseries,
    has_custom_parser,
)
from frappe.utils import cint, cstr, now_datetime

if TYPE_CHECKING:
    from frappe.model.document import Document


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
        # to parse naming series by fieldname
        .select("*")
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
        naming_series = parse_naming_series(
            item.naming_series.replace("#", ""), doc=item
        )
        item.serial_number = get_serial_number(item)
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


def _parse_naming_series(doc):
    naming_series = parse_naming_series(doc.naming_series, doc=doc)
    serial_number = get_serial_number(doc)
    return naming_series, serial_number


def parse_naming_series(
    parts: list[str] | str,
    doctype=None,
    doc: Optional["Document"] = None,
    number_generator: Callable[[str, int], str] | None = None,
) -> str:
    """Parse the naming series and get next name.

    args:
            parts: naming series parts (split by `.`)
            doc: document to use for series that have parts using fieldnames
            number_generator: Use different counter backend other than `tabSeries`. Primarily used for testing.
    """

    name = ""
    _sentinel = object()
    if isinstance(parts, str):
        parts = parts.split(".")

    if not number_generator:
        number_generator = getseries

    series_set = False
    today = doc.get("creation") if doc else now_datetime()
    for e in parts:
        if not e:
            continue

        part = ""
        if e.startswith("#"):
            if not series_set:
                digits = len(e)
                part = number_generator(name, digits)
                series_set = True
        elif e == "YY":
            part = today.strftime("%y")
        elif e == "MM":
            part = today.strftime("%m")
        elif e == "DD":
            part = today.strftime("%d")
        elif e == "YYYY":
            part = today.strftime("%Y")
        elif e == "WW":
            part = determine_consecutive_week_number(today)
        elif e == "timestamp":
            part = str(today)
        elif doc and (e.startswith("{") or doc.get(e, _sentinel) is not _sentinel):
            e = e.replace("{", "").replace("}", "")
            part = doc.get(e)
        elif method := has_custom_parser(e):
            part = frappe.get_attr(method[0])(doc, e)
        else:
            part = e

        if isinstance(part, str):
            name += part
        elif isinstance(part, NAMING_SERIES_PART_TYPES):
            name += cstr(part).strip()

    return name
