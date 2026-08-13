# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import frappe
from erpnext.accounts.report.sales_register.sales_register import _execute
from frappe import _
<<<<<<< HEAD
=======
from frappe.utils import getdate

from india_compliance.gst_india.utils.gstr_1 import Category
from india_compliance.gst_india.utils.gstr_1.gstr_1_data import GSTR1Invoices
>>>>>>> a4e0638 (refactor: gstr 1  (#4718))


def execute(filters=None):
    additional_table_columns = get_additional_table_columns()

    return _execute(
        filters,
        additional_table_columns,
    )


def get_additional_table_columns():
    overseas_enabled, reverse_charge_enabled = frappe.get_cached_value(
        "GST Settings",
        "GST Settings",
        ("enable_overseas_transactions", "enable_reverse_charge_in_sales"),
    )

    additional_table_columns = [
        {
            "fieldtype": "Data",
            "label": _("Billing Address GSTIN"),
            "fieldname": "billing_address_gstin",
            "width": 140,
        },
        {
            "fieldtype": "Data",
            "label": _("Company GSTIN"),
            "fieldname": "company_gstin",
            "width": 120,
        },
        {
            "fieldtype": "Data",
            "label": _("Place of Supply"),
            "fieldname": "place_of_supply",
            "width": 120,
        },
        {
            "fieldtype": "Data",
            "label": _("GST Category"),
            "fieldname": "gst_category",
            "width": 120,
        },
        {
            "fieldtype": "Data",
            "label": _("E-Commerce GSTIN"),
            "fieldname": "ecommerce_gstin",
            "width": 130,
        },
    ]

    if reverse_charge_enabled:
        additional_table_columns.insert(
            -2,
            {
                "fieldtype": "Check",
                "label": _("Is Reverse Charge"),
                "fieldname": "is_reverse_charge",
                "width": 120,
            },
        )

    if overseas_enabled:
        additional_table_columns.insert(
            -2,
            {
                "fieldtype": "Check",
                "label": _("Is Export With GST"),
                "fieldname": "is_export_with_gst",
                "width": 120,
            },
        )

<<<<<<< HEAD
    return additional_table_columns
=======
    columns.extend(
        [
            {
                "label": _("Is Return"),
                "fieldname": "is_return",
                "fieldtype": "Check",
                "width": 120,
            },
            {
                "label": _("Is Debit Note"),
                "fieldname": "is_debit_note",
                "fieldtype": "Check",
                "width": 120,
            },
        ]
    )

    if filters.summary_by == "Summary by Item":
        if gst_settings.enable_sales_through_ecommerce_operators:
            columns.append(
                {
                    "label": _("E-Commerce GSTIN"),
                    "fieldname": "ecommerce_gstin",
                    "fieldtype": "Data",
                    "width": 180,
                }
            )

        columns.append(
            {
                "label": _("Item Code"),
                "fieldname": "item_code",
                "fieldtype": "Link",
                "options": "Item",
                "width": 180,
            }
        )

    columns.extend(
        [
            {
                "label": _("Item Qty"),
                "fieldname": "qty",
                "fieldtype": "Data",
                "width": 100,
            },
            {
                "label": _("HSN Code"),
                "fieldname": "gst_hsn_code",
                "fieldtype": "Link",
                "options": "GST HSN Code",
                "width": 120,
            },
            # TODO: HSN Subcategory Column
            {
                "label": _("UOM"),
                "fieldname": "uom",
                "fieldtype": "Data",
                "width": 100,
            },
            {
                "label": _("GST Treatment"),
                "fieldname": "gst_treatment",
                "width": 120,
                "fieldtype": "Data",
            },
            {
                "label": _("Taxable Value"),
                "fieldname": "taxable_value",
                "width": 120,
                "fieldtype": "Currency",
                "options": company_currency,
            },
            {
                "label": _("GST Rate"),
                "fieldname": "gst_rate",
                "width": 120,
                "fieldtype": "Data",
            },
            {
                "label": _("CGST Amount"),
                "fieldname": "cgst_amount",
                "width": 120,
                "fieldtype": "Currency",
                "options": company_currency,
            },
            {
                "label": _("SGST Amount"),
                "fieldname": "sgst_amount",
                "width": 120,
                "fieldtype": "Currency",
                "options": company_currency,
            },
            {
                "label": _("IGST Amount"),
                "fieldname": "igst_amount",
                "width": 120,
                "fieldtype": "Currency",
                "options": company_currency,
            },
            {
                "label": _("Total Cess Amount"),
                "fieldname": "total_cess_amount",
                "width": 120,
                "fieldtype": "Currency",
                "options": company_currency,
            },
            {
                "label": _("Total Tax"),
                "fieldname": "total_tax",
                "width": 120,
                "fieldtype": "Currency",
                "options": company_currency,
            },
            {
                "label": _("Total Amount"),
                "fieldname": "total_amount",
                "width": 120,
                "fieldtype": "Currency",
                "options": company_currency,
            },
            {
                "label": _("Returned Invoice Total"),
                "fieldname": "returned_invoice_total",
                "width": 120,
                "fieldtype": "Currency",
                "options": company_currency,
            },
            {
                "label": _("Invoice Type"),
                "fieldname": "invoice_type",
                "width": 120,
                "fieldtype": "Data",
            },
        ]
    )

    if not filters.invoice_category or filters.invoice_category == Category.SUPECOM.value:
        columns.append(
            {
                "label": _("Invoice Category"),
                "fieldname": "invoice_category",
                "width": 120,
                "fieldtype": "Data",
            }
        )

    if not filters.invoice_sub_category or filters.invoice_category == Category.SUPECOM.value:
        columns.append(
            {
                "label": _("Invoice Sub Category"),
                "fieldname": "invoice_sub_category",
                "width": 120,
                "fieldtype": "Data",
            }
        )

    if filters.summary_by == "Summary by Item" and gst_settings.enable_sales_through_ecommerce_operators:
        columns.append(
            {
                "label": _("E-Commerce Supply Type"),
                "fieldname": "ecommerce_supply_type",
                "fieldtype": "Data",
                "width": 250,
            }
        )

    return columns
>>>>>>> a4e0638 (refactor: gstr 1  (#4718))
