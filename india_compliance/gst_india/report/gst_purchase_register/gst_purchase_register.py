# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from erpnext.accounts.report.purchase_register.purchase_register import _execute
from frappe import _

<<<<<<< HEAD
=======
from india_compliance.gst_india.utils.gstr3b.gstr3b_inward_data import GSTR3BInvoices
>>>>>>> 7a468667 (refactor: rename gstr3b data files)

def execute(filters=None):
    return _execute(filters, get_additional_table_columns())


def get_additional_table_columns():
    return [
        {
            "fieldtype": "Data",
            "label": _("Supplier GSTIN"),
            "fieldname": "supplier_gstin",
            "width": 120,
        },
        {
            "fieldtype": "Data",
            "label": _("Company GSTIN"),
            "fieldname": "company_gstin",
            "width": 120,
        },
        {
            "fieldtype": "Check",
            "label": _("Is Reverse Charge"),
            "fieldname": "is_reverse_charge",
            "width": 120,
        },
        {
            "fieldtype": "Data",
            "label": _("GST Category"),
            "fieldname": "gst_category",
            "width": 120,
        },
    ]
