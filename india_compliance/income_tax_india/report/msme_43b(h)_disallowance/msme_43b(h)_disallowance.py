# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from india_compliance.income_tax_india.utils.msme import get_msme_payables


def execute(filters: dict | None = None):
    filters = validate_filters(filters)

    data = get_data(filters)
    columns = get_columns()

    return columns, data


def validate_filters(filters):
    filters = frappe._dict(filters or {})
    if not filters.company:
        frappe.throw(_("Please select a Company"))

    if not (filters.from_date and filters.to_date):
        frappe.throw(_("Please select From Date and To Date"))

    if getdate(filters.from_date) > getdate(filters.to_date):
        frappe.throw(_("From Date cannot be after To Date"))

    filters.as_on_date = getdate(filters.as_on_date or nowdate())

    return filters


def get_data(filters):
    data = get_msme_payables(
        company=filters.company,
        from_date=filters.from_date,
        to_date=filters.to_date,
        supplier=filters.supplier,
        as_on_date=filters.as_on_date,
        enterprise_type=filters.enterprise_type,
        only_43b_applicable=True,
    )

    return [row for row in data if row["disallowable_amount"]]


def get_columns():
    return [
        {
            "label": _("Supplier"),
            "fieldname": "supplier",
            "fieldtype": "Link",
            "options": "Supplier",
            "width": 140,
        },
        {
            "label": _("Supplier Name"),
            "fieldname": "supplier_name",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": _("Enterprise Type"),
            "fieldname": "enterprise_type",
            "fieldtype": "Data",
            "width": 110,
        },
        {
            "label": _("UDYAM No."),
            "fieldname": "udyam_number",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": _("Voucher Type"),
            "fieldname": "voucher_type",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": _("Voucher No"),
            "fieldname": "voucher_no",
            "fieldtype": "Dynamic Link",
            "options": "voucher_type",
            "width": 160,
        },
        {
            "label": _("Posting Date"),
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "label": _("Due Date"),
            "fieldname": "due_date",
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "label": _("Voucher Amount"),
            "fieldname": "invoice_amount",
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "label": _("Paid"),
            "fieldname": "paid_amount",
            "fieldtype": "Currency",
            "width": 110,
        },
        {
            "label": _("Paid After Due (in-year)"),
            "fieldname": "paid_after_due",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "label": _("Payment Date"),
            "fieldname": "payment_date",
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "label": _("Outstanding"),
            "fieldname": "outstanding",
            "fieldtype": "Currency",
            "width": 110,
        },
        {
            "label": _("Days Overdue"),
            "fieldname": "days_overdue",
            "fieldtype": "Int",
            "width": 100,
        },
        {
            "label": _("Status"),
            "fieldname": "payment_status",
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "label": _("Disallowable u/s 43B(h)"),
            "fieldname": "disallowable_amount",
            "fieldtype": "Currency",
            "width": 160,
        },
    ]
