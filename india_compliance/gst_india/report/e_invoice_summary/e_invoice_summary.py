# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import Case


def execute(filters=None):
    validate_filters(filters)

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def validate_filters(filters=None):
    if filters is None:
        filters = {}
    filters = frappe._dict(filters)

    if not filters.company:
        frappe.throw(
            _("{} is mandatory for generating e-Invoice Summary Report").format(
                _("Company")
            ),
            title=_("Invalid Filter"),
        )
    if filters.company:
        # validate if company has e-invoicing enabled
        pass
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
        .inner_join(e_invoice_log)
        .on(sales_invoice.name == e_invoice_log.sales_invoice)
        .select(
            sales_invoice.posting_date,
            sales_invoice.einvoice_status,
            sales_invoice.customer,
            Case().when(sales_invoice.is_return == 1, "Y").else_("N").as_("is_return"),
            sales_invoice.base_grand_total,
            e_invoice_log.sales_invoice,
            e_invoice_log.acknowledgement_number,
            e_invoice_log.acknowledged_on,
            e_invoice_log.irn,
        )
        .where(
            sales_invoice.posting_date[
                filters.get("from_date") : filters.get("to_date")
            ]
        )
        .where(sales_invoice.company == filters.get("company"))
    )

    if filters.get("status"):
        query = query.where(sales_invoice.einvoice_status == filters.get("status"))

    if filters.get("customer"):
        query = query.where(sales_invoice.customer == filters.get("customer"))

    return query.run(as_dict=True)


def get_columns():
    return [
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
            "width": 140,
        },
        {
            "fieldtype": "Data",
            "fieldname": "einvoice_status",
            "label": _("Status"),
            "width": 100,
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
            "label": "Acknowledgement Number",
            "width": 145,
        },
        {
            "fieldtype": "Data",
            "fieldname": "acknowledged_on",
            "label": "Acknowledged On (IST)",
            "width": 165,
        },
        {"fieldtype": "Data", "fieldname": "irn", "label": _("IRN No."), "width": 250},
        {
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "fieldname": "base_grand_total",
            "label": _("Grand Total"),
            "width": 120,
        },
    ]
