# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe import _
from erpnext.accounts.report.item_wise_sales_register.item_wise_sales_register import (
    _execute,
)

from india_compliance.gst_india.report.gst_sales_register.gst_sales_register import (
    get_additional_table_columns as get_si_columns,
)


def execute(filters=None):
    return _execute(
        filters,
        get_additional_table_columns(),
        get_additional_conditions(filters),
    )


def get_additional_table_columns():
    additional_table_columns = get_si_columns()

    for row in additional_table_columns:
        row["_doctype"] = "Sales Invoice"

    additional_table_columns.append(
        {
            "fieldtype": "Data",
            "label": _("HSN Code"),
            "fieldname": "gst_hsn_code",
            "width": 120,
            "_doctype": "Sales Invoice Item",
        }
    )

    return additional_table_columns


def get_additional_conditions(filters):
    additional_conditions = ""
    if filters.get("company_gstin"):
        additional_conditions += (
            " AND `tabSales Invoice`.company_gstin = %(company_gstin)s"
        )

    return additional_conditions
