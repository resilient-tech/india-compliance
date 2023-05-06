# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe import _
from erpnext.accounts.report.item_wise_sales_register.item_wise_sales_register import (
    _execute,
)

from india_compliance.gst_india.report.gst_sales_register.gst_sales_register import (
    get_additional_table_columns,
    get_column_names,
)


def execute(filters=None):
    additional_table_columns = get_additional_table_columns()
    additional_table_columns.append(
        {
            "fieldtype": "Data",
            "label": _("HSN Code"),
            "fieldname": "gst_hsn_code",
            "width": 120,
        }
    )

    additional_query_columns = [
        row.get("fieldname") for row in additional_table_columns
    ]
    additional_conditions = get_conditions(filters, additional_query_columns)

    return _execute(
        filters,
        additional_table_columns,
        get_column_names(additional_table_columns),
        additional_conditions,
    )


def get_conditions(filters, additional_query_columns):
    conditions = ""

    for opts in additional_query_columns:
        if filters.get(opts):
            conditions += f" and {opts}=%({opts})s"

    return conditions
