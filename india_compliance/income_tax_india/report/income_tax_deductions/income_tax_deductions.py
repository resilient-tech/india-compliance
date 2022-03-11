# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe
from frappe import _
import erpnext
from erpnext.payroll.report.income_tax_deductions.income_tax_deductions import (
    execute as execute_erpnext_report,
)


def execute(filters=None, **kwargs):
    columns, data = execute_erpnext_report(filters=filters, **kwargs)
    if filters.get("company"):
        frappe.flags.company = filters["company"]

    # User may be using ERPNext version with India-specific features
    if erpnext.get_region() != "India" or any(
        column.get("fieldname") == "pan_number" for column in columns
    ):
        return columns, data

    return get_columns(columns), get_data(data)


def get_columns(columns):
    for index, column in enumerate(columns):
        if column.get("fieldname") == "employee_name":
            break

    columns.insert(
        index,
        {
            "label": _("Pan Number"),
            "fieldname": "pan_number",
            "fieldtype": "Data",
            "width": 140,
        },
    )

    return columns


def get_data(data):
    employees = [row.get("employee") for row in data]
    pan_numbers = frappe.get_all(
        "Employee",
        fields=("pan_number", "name"),
        filters={"name": ("in", employees)},
    )
    pan_numbers = {employee.name: employee.pan_number for employee in pan_numbers}

    for row in data:
        row["pan_number"] = pan_numbers.get(row.get("employee"))

    return data
