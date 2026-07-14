# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""Open dues to Micro & Small suppliers approaching the 45-day limit.

The operational companion to the 43B(h) disallowance report: pay these before
the clock runs out and the disallowance never happens. Once a due is overdue it
belongs to that report, not this one.

Settlement dates are not needed here - only what is still outstanding - so this
reuses ERPNext's Accounts Payable engine rather than the Payment Ledger.
"""

from erpnext.accounts.report.accounts_receivable.accounts_receivable import (
    ReceivablePayableReport,
)
from frappe import _
from frappe.utils import flt, getdate

from india_compliance.income_tax_india.utils.msme_report import MSMEReport


def execute(filters: dict | None = None):
    return MSMEPayablesDue(filters).run()


class MSMEPayablesDue(MSMEReport):
    def get_data(self):
        rows = []

        for due in self.get_open_dues():
            invoice = self.invoices[due.voucher_no]
            posting_date = getdate(due.posting_date)
            classification = self.get_classification(due.voucher_no, posting_date)

            if not self.is_applicable(classification):
                continue

            due_date = self.get_due_date(posting_date)
            days_remaining = (due_date - self.filters.as_on_date).days

            # already overdue: belongs to the 43B(h) disallowance report
            if days_remaining < 0:
                continue

            rows.append(
                {
                    "supplier": invoice.supplier,
                    "supplier_name": invoice.supplier_name,
                    "enterprise_type": classification.enterprise_type,
                    "voucher_type": due.voucher_type,
                    "voucher_no": due.voucher_no,
                    "posting_date": posting_date,
                    "due_date": due_date,
                    "days_remaining": days_remaining,
                    "outstanding": flt(due.outstanding),
                }
            )

        # most urgent first
        rows.sort(key=lambda row: row["due_date"])
        return rows

    def get_open_dues(self):
        """Open MSME invoices from ERPNext's Accounts Payable engine."""
        _columns, rows, *_rest = ReceivablePayableReport(
            {
                "company": self.filters.company,
                "report_date": self.filters.as_on_date,
                "party_type": "Supplier",
                "party": self.suppliers,
            }
        ).run({"account_type": "Payable", "naming_by": ["Buying Settings", "supp_master_name"]})

        # positive outstanding only: advances / credits are not dues
        return [
            row
            for row in rows
            if row.get("voucher_type") == "Purchase Invoice"
            and row.get("voucher_no") in self.invoices
            and flt(row.get("outstanding")) > 0
            and row.get("posting_date")
        ]

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
                "width": 130,
            },
        ]
