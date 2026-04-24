# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from erpnext.accounts.report.tds_payable_monthly.tds_payable_monthly import (
    execute as _execute,
)


def execute(filters=None):
    _columns, _data = _execute(filters)
    data = update_data(_data)
    columns = update_columns(_columns)

    return columns, data


def update_data(data):
    twc_info = _get_twc_info(data)
    for row in data:
        twc = twc_info.get(row.get("tax_withholding_category"), {})
        row.update(twc)

    return data


def update_columns(columns):
    columns[1:1] = get_india_columns()
    return columns


def get_india_columns():
    return [
        {
            "label": _("New Income Tax Section"),
            "fieldname": "tds_section",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": _("Old Income Tax Section"),
            "fieldname": "old_income_tax_section",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": _("Entity Type"),
            "fieldname": "entity_type",
            "fieldtype": "Data",
            "width": 120,
        },
    ]


def _get_twc_info(data):
    categories = {
        row.get("tax_withholding_category")
        for row in data
        if row.get("tax_withholding_category")
    }
    if not categories:
        return {}

    fieldnames = [row["fieldname"] for row in get_india_columns()]
    twc = frappe.qb.DocType("Tax Withholding Category")
    rows = (
        frappe.qb.from_(twc)
        .select(twc.name, *[twc[field] for field in fieldnames])
        .where(twc.name.isin(categories))
        .run(as_dict=True)
    )
    return {row.pop("name"): row for row in rows}
