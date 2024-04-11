# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate

from india_compliance.gst_india.utils.gstr_1.gstr_1_data import GSTR1Invoices


def execute(filters=None):
    filters = validate_filters(filters)
    data = get_data(filters)
    columns = get_columns(filters)

    return columns, data


def validate_filters(filters):
    filters = frappe._dict(filters)
    filters["from_date"] = filters.date_range[0]
    filters["to_date"] = filters.date_range[1]

    if filters.from_date and filters.to_date:
        if getdate(filters.from_date) > getdate(filters.to_date):
            frappe.throw(
                _("From Date must be before To Date"), title=_("Invalid Filter")
            )

    return filters


def get_data(filters):
    _class = GSTR1Invoices(filters)
    invoices = []

    if filters.summary_by == "Summary by Item":
        invoices = _class.get_invoices_for_item_wise_summary()

    if filters.summary_by == "Summary by HSN":
        invoices = _class.get_invoices_for_hsn_wise_summary()

    if filters.summary_by == "Overview":
        return _class.get_overview()

    if filters.invoice_category:
        return _class.get_filtered_invoices(
            invoices, filters.invoice_category, filters.invoice_sub_category
        )

    _class.process_invoices(invoices)

    return invoices


def get_columns(filters):
    columns = []

    if filters.summary_by == "Overview":
        columns.extend(
            [
                {"label": _("Description"), "fieldname": "description", "width": "240"},
                {
                    "label": _("No. of records"),
                    "fieldname": "no_of_records",
                    "width": "120",
                    "fieldtype": "Int",
                },
                {
                    "label": _("Taxable Value"),
                    "fieldname": "taxable_value",
                    "width": "120",
                    "fieldtype": "Currency",
                    "options": "Company:company:default_currency",
                },
                {
                    "label": _("IGST Amount"),
                    "fieldname": "igst_amount",
                    "width": "120",
                    "fieldtype": "Currency",
                    "options": "Company:company:default_currency",
                },
                {
                    "label": _("CGST Amount"),
                    "fieldname": "cgst_amount",
                    "width": "120",
                    "fieldtype": "Currency",
                    "options": "Company:company:default_currency",
                },
                {
                    "label": _("SGST Amount"),
                    "fieldname": "sgst_amount",
                    "width": "120",
                    "fieldtype": "Currency",
                    "options": "Company:company:default_currency",
                },
                {
                    "label": _("Total Cess Amount"),
                    "fieldname": "total_cess_amount",
                    "width": "120",
                    "fieldtype": "Currency",
                    "options": "Company:company:default_currency",
                },
            ]
        )

        return columns

    if not filters.company_gstin:
        columns.append(
            {
                "label": _("Company GSTIN"),
                "fieldname": "company_gstin",
                "width": 180,
            },
        )
    columns.extend(
        [
            {
                "label": _("Posting Date"),
                "fieldname": "posting_date",
                "width": 120,
            },
            {
                "label": _("Invoice Number"),
                "fieldname": "invoice_no",
                "fieldtype": "Link",
                "options": "Sales Invoice",
                "width": 150,
            },
            {
                "label": _("Customer Name"),
                "fieldname": "customer_name",
                "fieldtype": "Link",
                "options": "Customer",
                "width": 150,
            },
            {
                "label": _("GST Category"),
                "fieldname": "gst_category",
                "width": 120,
                "fieldtype": "Data",
            },
            {
                "label": _("Billing Address GSTIN"),
                "fieldname": "billing_address_gstin",
                "width": 180,
                "fieldtype": "Data",
            },
            {
                "label": _("Place of Supply"),
                "fieldname": "place_of_supply",
                "width": 120,
                "fieldtype": "Data",
            },
        ]
    )

    gst_settings = frappe.get_doc("GST Settings")

    if gst_settings.enable_reverse_charge_in_sales:
        columns.append(
            {
                "label": _("Is Reverse Charge"),
                "fieldname": "is_reverse_charge",
                "fieldtype": "Check",
                "width": 120,
            }
        )

    if gst_settings.enable_overseas_transactions:
        columns.append(
            {
                "label": _("Is Export with GST"),
                "fieldname": "is_export_with_gst",
                "fieldtype": "Check",
                "width": 120,
            }
        )

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
                "label": _("HSN Code"),
                "fieldname": "gst_hsn_code",
                "fieldtype": "Link",
                "options": "GST HSN Code",
                "width": 120,
            },
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
                "options": "Company:company:default_currency",
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
                "options": "Company:company:default_currency",
            },
            {
                "label": _("SGST Amount"),
                "fieldname": "sgst_amount",
                "width": 120,
                "fieldtype": "Currency",
                "options": "Company:company:default_currency",
            },
            {
                "label": _("IGST Amount"),
                "fieldname": "igst_amount",
                "width": 120,
                "fieldtype": "Currency",
                "options": "Company:company:default_currency",
            },
            {
                "label": _("Total Cess Amount"),
                "fieldname": "total_cess_amount",
                "width": 120,
                "fieldtype": "Currency",
                "options": "Company:company:default_currency",
            },
            {
                "label": _("Total Tax"),
                "fieldname": "total_tax",
                "width": 120,
                "fieldtype": "Currency",
                "options": "Company:company:default_currency",
            },
            {
                "label": _("Total Amount"),
                "fieldname": "total_amount",
                "width": 120,
                "fieldtype": "Currency",
                "options": "Company:company:default_currency",
            },
            {
                "label": _("Retured Invoice Total"),
                "fieldname": "returned_invoice_total",
                "width": 120,
                "fieldtype": "Currency",
                "options": "Company:company:default_currency",
            },
            {
                "label": _("Invoice Type"),
                "fieldname": "invoice_type",
                "width": 120,
                "fieldtype": "Data",
            },
        ]
    )
    if not filters.invoice_category:
        columns.append(
            {
                "label": _("Invoice Category"),
                "fieldname": "invoice_category",
                "width": 120,
                "fieldtype": "Data",
            }
        )
    if not filters.invoice_sub_category:
        columns.append(
            {
                "label": _("Invoice Sub Category"),
                "fieldname": "invoice_sub_category",
                "width": 120,
                "fieldtype": "Data",
            }
        )

    return columns
