# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import IfNull


def execute(filters=None):
    validate_filters(filters)

    columns = get_columns(filters)
    data = get_data(filters)

    return columns, data


def validate_filters(filters=None):
    if filters is None:
        filters = {}

    filters = frappe._dict(filters)

    settings = frappe.get_cached_doc("GST Settings")

    if not settings.enable_e_invoice:
        frappe.throw(
            _("e-Invoice is not enabled for your company."),
            title=_("Invalid Filter"),
        )

    if not filters.from_date or not filters.to_date:
        frappe.throw(
            _(
                "From Date & To Date is mandatory for generating e-Invoice Summary"
                " Report"
            ),
            title=_("Invalid Filter"),
        )
    if filters.from_date > filters.to_date:
        frappe.throw(_("From Date must be before To Date"), title=_("Invalid Filter"))


def get_data(filters=None):
    sales_invoice = frappe.qb.DocType("Sales Invoice")
    e_invoice_log = frappe.qb.DocType("e-Invoice Log")

    query = (
        frappe.qb.from_(sales_invoice)
        .left_join(e_invoice_log)
        .on(sales_invoice.irn == e_invoice_log.irn)
        .select(
            sales_invoice.posting_date,
            sales_invoice.einvoice_status,
            sales_invoice.customer,
            Case().when(sales_invoice.is_return == 1, "Y").else_("N").as_("is_return"),
            sales_invoice.base_grand_total,
            sales_invoice.name.as_("sales_invoice"),
            sales_invoice.irn,
            sales_invoice.company,
            e_invoice_log.acknowledgement_number,
            e_invoice_log.acknowledged_on,
            Case()
            .when(sales_invoice.docstatus == 1, "Submitted")
            .else_("Cancelled")
            .as_("docstatus"),
        )
        .where(
            sales_invoice.posting_date[
                filters.get("from_date") : filters.get("to_date")
            ]
        )
        .where(IfNull(sales_invoice.einvoice_status, "") != "")
        .where(sales_invoice.docstatus != 0)
        .where(sales_invoice.is_opening != "Yes")
    )

    if filters.get("company"):
        query = query.where(sales_invoice.company == filters.get("company"))

    if filters.get("status"):
        query = query.where(sales_invoice.einvoice_status == filters.get("status"))

    if filters.get("customer"):
        query = query.where(sales_invoice.customer == filters.get("customer"))

    return query.run(as_dict=True)


def get_columns(filters=None):
    columns = [
        {
            "fieldtype": "Date",
            "fieldname": "posting_date",
            "label": _("Posting Date"),
            "width": 0,
        },
        {
            "fieldtype": "Link",
            "fieldname": "sales_invoice",
            "label": _("Sales Invoice"),
            "options": "Sales Invoice",
            "width": 130,
        },
        {
            "fieldtype": "Data",
            "fieldname": "einvoice_status",
            "label": _("e-Invoice Status"),
            "width": 130,
        },
        {
            "fieldtype": "Link",
            "fieldname": "customer",
            "options": "Customer",
            "label": _("Customer"),
        },
        {
            "fieldtype": "Data",
            "fieldname": "is_return",
            "label": _("Is Return"),
            "width": 85,
        },
        {
            "fieldtype": "Data",
            "fieldname": "acknowledgement_number",
            "label": _("Acknowledgement Number"),
            "width": 110,
        },
        {
            "fieldtype": "Datetime",
            "fieldname": "acknowledged_on",
            "label": _("Acknowledged On (IST)"),
            "width": 110,
        },
        {"fieldtype": "Data", "fieldname": "irn", "label": _("IRN No."), "width": 250},
        {
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "fieldname": "base_grand_total",
            "label": _("Grand Total"),
            "width": 120,
        },
        {
            "fieldtype": "Data",
            "fieldname": "docstatus",
            "label": _("Document Status"),
            "width": 100,
        },
    ]

    if not filters.get("company"):
        columns.append(
            {
                "fieldtype": "Link",
                "fieldname": "company",
                "options": "Company",
                "label": _("Company"),
                "width": 120,
            },
        )

    return columns
