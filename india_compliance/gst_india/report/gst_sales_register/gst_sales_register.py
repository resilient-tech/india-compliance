# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import frappe
from erpnext.accounts.report.sales_register.sales_register import _execute
from frappe import _


def execute(filters=None):
    additional_table_columns = get_additional_table_columns()

<<<<<<< HEAD
    return _execute(
        filters,
        additional_table_columns,
=======
    return columns, data


def validate_filters(filters):
    filters = frappe._dict(filters)
    filters["from_date"] = filters.date_range[0]
    filters["to_date"] = filters.date_range[1]

    if filters.from_date and filters.to_date and getdate(filters.from_date) > getdate(filters.to_date):
        frappe.throw(_("From Date must be before To Date"), title=_("Invalid Filter"))

    return filters


def get_data(filters):
    gstr1_invoices = GSTR1Invoices(filters)
    invoices = []

    if filters.summary_by == "Summary by Item":
        invoices = gstr1_invoices.get_invoices_for_item_wise_summary()

    if filters.summary_by == "Summary by HSN":
        invoices = gstr1_invoices.get_invoices_for_hsn_wise_summary()

    if filters.summary_by == "Overview":
        return gstr1_invoices.get_overview()

    if filters.invoice_category:
        return gstr1_invoices.get_filtered_invoices(
            invoices, filters.invoice_category, filters.invoice_sub_category
        )

    gstr1_invoices.process_invoices(invoices)

    return invoices


def get_columns(filters):
    columns = []
    company_currency = frappe.get_cached_value("Company", filters.get("company"), "default_currency")

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
                    "options": company_currency,
                },
                {
                    "label": _("IGST Amount"),
                    "fieldname": "igst_amount",
                    "width": "120",
                    "fieldtype": "Currency",
                    "options": company_currency,
                },
                {
                    "label": _("CGST Amount"),
                    "fieldname": "cgst_amount",
                    "width": "120",
                    "fieldtype": "Currency",
                    "options": company_currency,
                },
                {
                    "label": _("SGST Amount"),
                    "fieldname": "sgst_amount",
                    "width": "120",
                    "fieldtype": "Currency",
                    "options": company_currency,
                },
                {
                    "label": _("Total Cess Amount"),
                    "fieldname": "total_cess_amount",
                    "width": "120",
                    "fieldtype": "Currency",
                    "options": company_currency,
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
>>>>>>> df75760 (refactor: rename _class variables to descriptive names)
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

    return additional_table_columns
