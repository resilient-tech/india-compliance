# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from india_compliance.gst_india.utils.itc_04.itc_04_data import ITC04Query


def execute(filters=None):
    report = JobWorkMovement(filters)
    return report.columns(), report.data()


class JobWorkMovement:
    def __init__(self, filters=None):
        self.filters = filters
        self.validate_filters()

    def validate_filters(self):
        if not self.filters:
            self.filters = frappe._dict()

        if not self.filters.category:
            frappe.throw(_("Category is mandatory"))

        if not self.filters.from_date:
            frappe.throw(_("From Date is mandatory"))

        if not self.filters.to_date:
            frappe.throw(_("To Date is mandatory"))

        if self.filters.from_date > self.filters.to_date:
            frappe.throw(_("From Date cannot be greater than To Date"))

    def data(self):
        itc04 = ITC04Query(self.filters)
        data = []

        if self.filters.category == "Sent for Job Work (Table 4)":
            data = itc04.get_query_table_4_se().run(as_dict=True)
            data.extend(itc04.get_query_table_4_sr().run(as_dict=True))

        elif self.filters.category == "Received back from Job Worker (Table 5A)":
            data = itc04.get_query_table_5A_se().run(as_dict=True)
            data.extend(itc04.get_query_table_5A_sr().run(as_dict=True))

        return data

    def columns(self):
        if self.filters.category == "Sent for Job Work (Table 4)":
            return self.get_columns_table_4()

        elif self.filters.category == "Received back from Job Worker (Table 5A)":
            return self.get_columns_table_5A()

        return []

    def get_columns_table_4(self):
        return [
            *self.gstin_column(),
            *self.posting_date_column(),
            {
                "fieldname": "invoice_no",
                "label": _("Invoice No (Challan No)"),
                "fieldtype": "Dynamic Link",
                "options": "invoice_type",
                "width": 180,
            },
            *self.common_columns(),
            {
                "fieldname": "taxable_value",
                "label": _("Taxable Value"),
                "fieldtype": "Currency",
                "width": 150,
            },
            {
                "fieldname": "gst_rate",
                "label": _("GST Rate"),
                "fieldtype": "Percent",
                "width": 100,
            },
            {
                "fieldname": "cgst_amount",
                "label": _("CGST Amount"),
                "fieldtype": "Currency",
                "width": 120,
            },
            {
                "fieldname": "sgst_amount",
                "label": _("SGST Amount"),
                "fieldtype": "Currency",
                "width": 120,
            },
            {
                "fieldname": "igst_amount",
                "label": _("IGST Amount"),
                "fieldtype": "Currency",
                "width": 120,
            },
            {
                "fieldname": "total_cess_amount",
                "label": _("Cess Amount"),
                "fieldtype": "Currency",
                "width": 120,
            },
            {
                "fieldname": "total_tax",
                "label": _("Total Tax"),
                "fieldtype": "Currency",
                "width": 120,
            },
            {
                "fieldname": "total_amount",
                "label": _("Total Amount"),
                "fieldtype": "Currency",
                "width": 150,
            },
            {
                "fieldname": "gst_treatment",
                "label": _("GST Treatment"),
                "fieldtype": "Data",
                "width": 120,
            },
        ]

    def get_columns_table_5A(self):
        return [
            *self.gstin_column(),
            *self.posting_date_column(),
            {
                "fieldname": "original_challan_no",
                "label": _("Original Challan No"),
                "fieldtype": "Dynamic Link",
                "options": "original_challan_invoice_type",
                "width": 180,
            },
            {
                "fieldname": "invoice_no",
                "label": _("Job Worker Invoice No (Challan No)"),
                "fieldtype": "Dynamic Link",
                "options": "invoice_type",
                "width": 180,
            },
            *self.common_columns(),
        ]

    def gstin_column(self):
        return [
            {
                "fieldname": "company_gstin",
                "label": _("Company GSTIN"),
                "fieldtype": "Data",
                "width": 160,
                "hidden": True if self.filters.company_gstin else False,
            }
        ]

    def posting_date_column(self):
        return [
            {
                "fieldname": "posting_date",
                "label": _("Posting Date"),
                "fieldtype": "Date",
                "width": 120,
            }
        ]

    def common_columns(self):
        return [
            {
                "fieldname": "supplier",
                "label": _("Job Worker"),
                "fieldtype": "Link",
                "options": "Supplier",
                "width": 200,
            },
            {
                "fieldname": "supplier_gstin",
                "label": _("Job Worker GSTIN"),
                "fieldtype": "Data",
                "width": 160,
            },
            {
                "fieldname": "place_of_supply",
                "label": _("Place of Supply"),
                "fieldtype": "Data",
                "width": 150,
            },
            {
                "fieldname": "is_return",
                "label": _("Is Return"),
                "fieldtype": "Check",
                "width": 90,
            },
            {
                "fieldname": "item_type",
                "label": _("Item Type (Input/Capital Goods)"),
                "fieldtype": "Data",
                "width": 180,
                "hidden": (
                    False
                    if self.filters.category == "Sent for Job Work (Table 4)"
                    else True
                ),
            },
            {
                "fieldname": "item_code",
                "label": _("Item Code"),
                "fieldtype": "Link",
                "options": "Item",
                "width": 180,
            },
            {
                "fieldname": "gst_hsn_code",
                "label": _("HSN Code"),
                "fieldtype": "Link",
                "options": "GST HSN Code",
                "width": 100,
            },
            {
                "fieldname": "qty",
                "label": _("Qty"),
                "fieldtype": "Float",
                "width": 90,
            },
            {
                "fieldname": "uom",
                "label": _("UOM"),
                "fieldtype": "Data",
                "width": 90,
            },
        ]
