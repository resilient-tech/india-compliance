# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""MSME Form-1: the half-yearly return of outstanding dues to MSE suppliers.

Filed under the MSMED Act, which has no trader carve-out - that exclusion is a
Section 43B(h) income-tax concept. Traders are therefore included by default,
and the filter lets the accountant decide otherwise.
"""

import frappe
from frappe import _
from frappe.utils import add_months, get_last_day

from india_compliance.income_tax_india.utils.msme import get_financial_year_dates
from india_compliance.income_tax_india.utils.msme_report import MSMEPayablesReport

PERIODS = {"Apr-Sep": 0, "Oct-Mar": 6}

BUCKETS = (
    ("paid_within_due", "Paid within 45 days"),
    ("paid_after_due", "Paid after 45 days"),
    ("outstanding_not_due", "Outstanding for 45 days or less"),
    ("outstanding_overdue", "Outstanding for more than 45 days"),
)


def execute(filters: dict | None = None):
    return MSMEForm1(filters).run()


class MSMEForm1(MSMEPayablesReport):
    def validate_filters(self):
        super().validate_filters()

        if not self.filters.period_fy:
            frappe.throw(_("Please select a Financial Year"))

        if self.filters.period and self.filters.period not in PERIODS:
            frappe.throw(_("Please select a valid Period"))

        self.filters.group_by = self.filters.group_by or "Invoice Wise"
        self.filters.period_start, self.filters.period_end = get_period_dates(
            self.filters.period_fy, self.filters.period
        )

        # the report is as on the period end, and only counts payments made
        # within the period
        self.filters.to_date = self.filters.period_end
        self.filters.as_on_date = self.filters.period_end
        self.settlement_from_date = self.filters.period_start

        # MSMED Act covers traders; 43B(h) is what excludes them
        self.exclude_traders = not self.filters.include_traders

    def get_data(self):
        rows = self.get_invoice_rows()

        if self.filters.group_by != "Invoice Wise":
            rows = self.group_by_supplier(rows)

        return rows

    def get_invoice_rows(self):
        # Form-1 reports dues against supplies: skip unadjusted payment / credit
        # rows (negative) and vouchers with no period activity and no dues.
        return [
            row
            for row in self.get_payables()
            if row["invoice_amount"] > 0
            and (row["paid_within_due"] or row["paid_after_due"] or row["outstanding"])
        ]

    def group_by_supplier(self, rows):
        """Aggregate into the supplier-wise MCA annexure shape.

        Each bucket gets a No. (count of invoices with an amount in that bucket)
        and a total amount, per supplier.
        """
        suppliers = {}
        for row in rows:
            supplier = suppliers.setdefault(
                row["supplier"],
                {
                    "supplier": row["supplier"],
                    "supplier_name": row["supplier_name"],
                    "pan": row["pan"],
                    **{fieldname: 0 for fieldname, _label in BUCKETS},
                    **{f"{fieldname}_count": 0 for fieldname, _label in BUCKETS},
                },
            )

            for fieldname, _label in BUCKETS:
                if row[fieldname]:
                    supplier[fieldname] += row[fieldname]
                    supplier[f"{fieldname}_count"] += 1

        return list(suppliers.values())

    def get_columns(self):
        columns = [
            {
                "label": _("Name of MSE Supplier"),
                "fieldname": "supplier",
                "fieldtype": "Link",
                "options": "Supplier",
                "width": 180,
            },
            {
                "label": _("PAN of the Supplier"),
                "fieldname": "pan",
                "fieldtype": "Data",
                "width": 120,
            },
        ]

        if self.filters.group_by == "Invoice Wise":
            columns += [
                {
                    "label": _("Voucher No"),
                    "fieldname": "voucher_no",
                    "fieldtype": "Dynamic Link",
                    "options": "voucher_type",
                    "width": 160,
                },
                {
                    "label": _("Date from which Due"),
                    "fieldname": "due_date",
                    "fieldtype": "Date",
                    "width": 120,
                },
                *(
                    {
                        "label": _(label),
                        "fieldname": fieldname,
                        "fieldtype": "Currency",
                        "width": 150,
                    }
                    for fieldname, label in BUCKETS
                ),
            ]

            return columns

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

        return columns


def get_period_dates(period_fy, period=None):
    fy_start, fy_end = get_financial_year_dates(period_fy)

    # No period selected -> cover the whole financial year (Apr-Mar).
    if not period:
        return fy_start, fy_end

    start = add_months(fy_start, PERIODS[period])
    return start, get_last_day(add_months(start, 5))
