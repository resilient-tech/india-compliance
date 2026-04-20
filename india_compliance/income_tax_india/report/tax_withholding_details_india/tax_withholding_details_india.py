# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from erpnext.accounts.report.tax_withholding_details.tax_withholding_details import (
    _execute,
)
from frappe import _


def execute(filters=None):
    return _execute(filters, additional_table_columns=get_additional_table_columns())


def get_additional_table_columns():
    return [
        {
            "label": _("New Income Tax Section"),
            "fieldname": "tds_section",
            "fieldtype": "Data",
            "width": 120,
            "_doctype": "Tax Withholding Category",
        },
        {
            "label": _("Old Income Tax Section"),
            "fieldname": "old_income_tax_section",
            "fieldtype": "Data",
            "width": 150,
            "_doctype": "Tax Withholding Category",
        },
        {
            "label": _("Entity Type"),
            "fieldname": "entity_type",
            "fieldtype": "Data",
            "width": 120,
            "_doctype": "Tax Withholding Category",
        },
    ]
