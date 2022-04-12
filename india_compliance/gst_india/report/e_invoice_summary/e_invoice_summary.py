# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _


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
    conditions = get_conditions(filters)

    data = frappe.db.sql(
        """
        SELECT
            si.posting_date,
            einv_log.sales_invoice,
            si.einvoice_status,
            si.customer,
            si.is_return,
            einv_log.acknowledgement_number,
            einv_log.acknowledged_on,
            einv_log.irn,
            si.base_grand_total
        FROM
            `tabSales Invoice` as si,
            `tabe-Invoice Log` as einv_log
        WHERE
            si.name = einv_log.sales_invoice
            {0}
    """.format(
            conditions
        )
    )

    return data


def get_conditions(filters=None):
    conditions = ""

    conditions += " AND si.posting_date BETWEEN %s and %s" % (
        frappe.db.escape(filters.get("from_date")),
        frappe.db.escape(filters.get("to_date")),
    )

    conditions += " AND si.company = {0}".format(
        frappe.db.escape(filters.get("company"))
    )

    if filters.get("status"):
        conditions += " AND si.einvoice_status = {0}".format(
            frappe.db.escape(filters.get("status"))
        )

    if filters.get("customer"):
        conditions += " AND si.customer = {0}".format(
            frappe.db.escape(filters.get("customer"))
        )

    return conditions


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
            "fieldname": "name",
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
            "fieldtype": "Check",
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
