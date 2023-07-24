# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


from frappe import _
from erpnext.accounts.report.item_wise_purchase_register.item_wise_purchase_register import (
    _execute,
)

from india_compliance.gst_india.report.gst_purchase_register.gst_purchase_register import (
    get_additional_table_columns as get_pi_columns,
)


def execute(filters=None):
    return _execute(filters, get_additional_table_columns())


def get_additional_table_columns():
    additional_table_columns = get_pi_columns()

    for row in additional_table_columns:
        row["_doctype"] = "Purchase Invoice"

    additional_table_columns.extend(
        [
            {
                "fieldtype": "Data",
                "label": _("HSN Code"),
                "fieldname": "gst_hsn_code",
                "width": 120,
                "_doctype": "Purchase Invoice Item",
            },
            {
                "fieldtype": "Data",
                "label": _("Supplier Invoice No"),
                "fieldname": "bill_no",
                "width": 120,
                "_doctype": "Purchase Invoice",
            },
            {
                "fieldtype": "Date",
                "label": _("Supplier Invoice Date"),
                "fieldname": "bill_date",
                "width": 100,
                "_doctype": "Purchase Invoice",
            },
        ]
    )

    return additional_table_columns
