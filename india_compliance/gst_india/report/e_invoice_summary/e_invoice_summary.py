# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from functools import reduce

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Coalesce, IfNull
from frappe.utils.data import get_datetime

from india_compliance.gst_india.utils.e_invoice import get_e_invoice_applicability_date


def execute(filters=None):
    validate_filters(filters)

    columns = get_columns(filters)
    data = get_data_for_all_companies(filters)

    return columns, data


def get_data_for_all_companies(filters):
    data = []

    indian_companies = []

    if filters.get("company"):
        indian_companies.append(filters.get("company"))
    else:
        indian_companies = frappe.get_all(
            "Company", filters={"country": "India"}, pluck="name"
        )

    for company in indian_companies:
        filters.company = company
        data.extend(get_data(filters))

    return sorted(data, key=lambda x: x.posting_date, reverse=True)


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

    if not filters.get("company"):
        return

    e_invoice_applicability_date = get_e_invoice_applicability_date(filters, settings)

    if not e_invoice_applicability_date:
        frappe.throw(
            _("As per your GST Settings, e-Invoice is not applicable for {}.").format(
                filters.company
            ),
            title=_("Invalid Filter"),
        )

    if get_datetime(filters.from_date) < get_datetime(e_invoice_applicability_date):
        frappe.msgprint(
            _("As per your GST Settings, e-Invoice is applicable from {}.").format(
                e_invoice_applicability_date
            ),
            alert=True,
        )


def get_data(filters=None):
    sales_invoice = frappe.qb.DocType("Sales Invoice")
    e_invoice_log = frappe.qb.DocType("e-Invoice Log")
    settings = frappe.get_cached_doc("GST Settings")
    e_invoice_applicability_date = get_e_invoice_applicability_date(filters, settings)

    if not settings.enable_e_invoice or not e_invoice_applicability_date:
        return []

    conditions = e_invoice_conditions(e_invoice_applicability_date)

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
        .where(sales_invoice.company == filters.get("company"))
        .where(conditions)
    )

    if filters.get("status"):
        query = query.where(sales_invoice.einvoice_status == filters.get("status"))

    if filters.get("customer"):
        query = query.where(sales_invoice.customer == filters.get("customer"))

    if not filters.get("exceptions"):
        data = query.where(sales_invoice.docstatus == 1).run(as_dict=True)
        cancelled_active_e_invoices = get_cancelled_active_e_invoice_query(
            filters, sales_invoice, query
        ).run(as_dict=True)

        return sorted(data + cancelled_active_e_invoices, key=lambda x: x.posting_date)

    if filters.get("exceptions") == "e-Invoice Not Generated":
        query = query.where(
            ((IfNull(sales_invoice.irn, "") == "") & (sales_invoice.docstatus == 1))
        )

    if filters.get("exceptions") == "Invoice Cancelled but not e-Invoice":
        # invoice is cancelled but irn is not cancelled
        query = get_cancelled_active_e_invoice_query(filters, sales_invoice, query)

    return query.run(as_dict=True)


def get_cancelled_active_e_invoice_query(filters, sales_invoice, query):
    query = query.where(
        (sales_invoice.docstatus == 2) & (IfNull(sales_invoice.irn, "") != "")
    )

    valid_irns = frappe.get_all(
        "Sales Invoice",
        pluck="irn",
        filters={
            "docstatus": 1,
            "company": filters.get("company"),
            # logical optimization
            "posting_date": [">=", filters.get("from_date")],
            "irn": ["is", "set"],
        },
    )

    if valid_irns:
        query = query.where(sales_invoice.irn.notin(valid_irns))
    return query


def e_invoice_conditions(e_invoice_applicability_date):
    sales_invoice = frappe.qb.DocType("Sales Invoice")
    taxable_invoices = validate_sales_invoice_item()
    conditions = []

    conditions.append(sales_invoice.posting_date >= e_invoice_applicability_date)
    conditions.append(
        sales_invoice.company_gstin != sales_invoice.billing_address_gstin
    )
    conditions.append(
        (
            (Coalesce(sales_invoice.place_of_supply, "") == "96-Other Countries")
            | (Coalesce(sales_invoice.billing_address_gstin, "") != "")
        )
    )
    conditions.append(sales_invoice.name.isin(taxable_invoices))

    return reduce(lambda a, b: a & b, conditions)


def validate_sales_invoice_item():
    sales_invoice_item = frappe.qb.DocType("Sales Invoice Item")

    taxable_invoices = (
        frappe.qb.from_(sales_invoice_item)
        .select(sales_invoice_item.parent)
        .where(sales_invoice_item.parenttype == "Sales Invoice")
        .where(sales_invoice_item.gst_treatment.isin(["Taxable", "Zero-Rated"]))
        .distinct()
    )

    return taxable_invoices


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
            "width": 90,
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
