# Copyright (c) 2022, Resilient Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe import _


def execute(filters=None):
    columns, data = get_columns(), [{"account": _("Opening")}]
    return columns, data


def get_data(filters):
    data = []
    return data


def get_columns():
    return [
        {
            "fieldname": "account",
            "label": _("Account"),
            "fieldtype": "Link",
            "options": "Account",
            "width": 200,
        },
        {
            "fieldname": "opening_debit",
            "label": _("Opening (Dr)"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 120,
        },
        {
            "fieldname": "opening_credit",
            "label": _("Opening (Cr)"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 120,
        },
        {
            "fieldname": "debit",
            "label": _("Debit"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 120,
        },
        {
            "fieldname": "credit",
            "label": _("Credit"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 120,
        },
        {
            "fieldname": "closing_debit",
            "label": _("Closing (Dr)"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 120,
        },
        {
            "fieldname": "closing_credit",
            "label": _("Closing (Cr)"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 120,
        },
    ]
