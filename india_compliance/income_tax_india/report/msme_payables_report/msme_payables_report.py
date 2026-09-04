# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days

from india_compliance.income_tax_india.utils.msme import MSME_PAYMENT_DAYS
from india_compliance.income_tax_india.utils.msme_report import MSMEPayablesReport


def execute(filters: dict | None = None):
    return MSMEPayablesDue(filters).run()


class MSMEPayablesDue(MSMEPayablesReport):
    """Open dues still within the Section 15 limit, most urgent first.

    The position is taken from the Payment Ledger as on the report date, so a
    payment made after it does not erase a due that was outstanding then.
    """

    def get_invoices_query(self):
        pi = frappe.qb.DocType("Purchase Invoice")

        # a supply accepted earlier than the outer limit cannot still be within
        # it on the report date, whatever its own limit is
        return (
            super()
            .get_invoices_query()
            .where(pi.posting_date >= add_days(self.filters.as_on_date, -MSME_PAYMENT_DAYS))
        )

    def get_data(self):
        rows = []

        for row in self.get_payables():
            # overdue belongs to the disallowance report; settled has nothing to pay
            if not row["outstanding_not_due"]:
                continue

            row["days_remaining"] = (row["due_date"] - self.filters.as_on_date).days
            rows.append(row)

        # most urgent first
        rows.sort(key=lambda row: row["due_date"])
        return rows

    def get_columns(self):
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
                "label": _("Days Remaining"),
                "fieldname": "days_remaining",
                "fieldtype": "Int",
                "width": 110,
            },
            {
                "label": _("Outstanding"),
                "fieldname": "outstanding",
                "fieldtype": "Currency",
                "options": "currency",
                "width": 130,
            },
        ]
