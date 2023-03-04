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

    return _execute(
        filters,
        additional_table_columns,
        get_column_names(additional_table_columns),
    )
