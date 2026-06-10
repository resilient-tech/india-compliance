# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.utils import add_months, get_last_day

from india_compliance.income_tax_india.utils.msme import (
    get_fiscal_year_dates,
    get_msme_payables,
)

PERIODS = {"Apr-Sep": 0, "Oct-Mar": 6}

BUCKETS = (
    ("paid_within_due", "Paid within 45 days"),
    ("paid_after_due", "Paid after 45 days"),
    ("outstanding_not_due", "Outstanding for 45 days or less"),
    ("outstanding_overdue", "Outstanding for more than 45 days"),
)


def execute(filters: dict | None = None):
    filters = validate_filters(filters)

    data = get_data(filters)
    columns = get_columns(filters)

    return columns, data


def validate_filters(filters):
    filters = frappe._dict(filters or {})
    if not filters.company:
        frappe.throw(_("Please select a Company"))

    if not filters.period_fy:
        frappe.throw(_("Please select a Financial Year"))

    if filters.period and filters.period not in PERIODS:
        frappe.throw(_("Please select a valid Period"))

    filters.period_start, filters.period_end = get_period_dates(filters.period_fy, filters.period)

    return filters


def get_period_dates(period_fy, period=None):
    fy_start, fy_end = get_fiscal_year_dates(period_fy)
    # No period selected -> cover the whole financial year (Apr-Mar).
    if not period:
        return fy_start, fy_end

    start = add_months(fy_start, PERIODS[period])
    return start, get_last_day(add_months(start, 5))


def get_data(filters):
    data = get_invoice_rows(filters)

    if filters.group_by != "Invoice Wise":
        data = group_by_supplier(data)

    return data


def get_invoice_rows(filters):
    payables = get_msme_payables(
        company=filters.company,
        to_date=filters.period_end,
        as_on_date=filters.period_end,
        only_43b_applicable=True,
        settlement_from_date=filters.period_start,
    )

    # Form-1 reports dues against supplies: skip unadjusted payment / credit
    # rows (negative) and vouchers with no period activity and no dues.
    return [
        row
        for row in payables
        if row["invoice_amount"] > 0
        and (row["paid_within_due"] or row["paid_after_due"] or row["outstanding"])
    ]


def group_by_supplier(rows):
    """Aggregate invoice rows into the supplier-wise MCA annexure shape.

    Each bucket gets a No. (count of invoices with an amount in that bucket)
    and a total amount, per supplier.
    """
    suppliers = {}
    for row in rows:
        agg = suppliers.setdefault(
            row["supplier"],
            {
                "supplier": row["supplier"],
                "supplier_name": row["supplier_name"],
                "pan": row["pan"],
                "reason_for_delay": "",
                **{fieldname: 0 for fieldname, _label in BUCKETS},
                **{f"{fieldname}_count": 0 for fieldname, _label in BUCKETS},
            },
        )
        for fieldname, _label in BUCKETS:
            if row[fieldname]:
                agg[fieldname] += row[fieldname]
                agg[f"{fieldname}_count"] += 1

    return list(suppliers.values())


def get_columns(filters):
    columns = [
        {
            "label": _("Name of MSE Supplier"),
            "fieldname": "supplier",
            "fieldtype": "Link",
            "options": "Supplier",
            "width": 180,
        },
        {"label": _("PAN of the Supplier"), "fieldname": "pan", "fieldtype": "Data", "width": 120},
    ]

    if filters.group_by == "Invoice Wise":
        columns += [
            {
                "label": _("Voucher No"),
                "fieldname": "voucher_no",
                "fieldtype": "Dynamic Link",
                "options": "voucher_type",
                "width": 160,
            },
            {"label": _("Date from which Due"), "fieldname": "due_date", "fieldtype": "Date", "width": 120},
        ]
        columns += [
            {"label": _(label), "fieldname": fieldname, "fieldtype": "Currency", "width": 150}
            for fieldname, label in BUCKETS
        ]
    else:
        # MCA annexure: a count (No.) and amount per bucket
        for fieldname, label in BUCKETS:
            columns += [
                {
                    "label": _("No. - {0}").format(_(label)),
                    "fieldname": f"{fieldname}_count",
                    "fieldtype": "Int",
                    "width": 90,
                },
                {
                    "label": _("Amount (Rs.) - {0}").format(_(label)),
                    "fieldname": fieldname,
                    "fieldtype": "Currency",
                    "width": 160,
                },
            ]

    columns.append(
        {
            "label": _("Reason for delay in payment / amount outstanding"),
            "fieldname": "reason_for_delay",
            "fieldtype": "Data",
            "width": 200,
        }
    )
    return columns
