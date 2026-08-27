# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate

from india_compliance.income_tax_india.utils.msme import MSME_UNCLASSIFIED
from india_compliance.income_tax_india.utils.msme_report import MSMEReport


def execute(filters: dict | None = None):
    return MSMEPayablesDue(filters).run()


class MSMEPayablesDue(MSMEReport):
    def get_invoices_query(self):
        pi = frappe.qb.DocType("Purchase Invoice")
        return super().get_invoices_query().where(pi.outstanding_amount > 0)

    def get_data(self):
        rows = []

        for invoice in self.invoices.values():
            posting_date = getdate(invoice.posting_date)
            classification = self.get_msme_status(invoice.msme_registration, posting_date)

            if not self.is_applicable(classification):
                continue

            due_date = self.get_msme_due_date(posting_date, invoice.due_date, classification)
            days_remaining = (due_date - self.filters.as_on_date).days

            # already overdue: belongs to the 43B(h) disallowance report
            if days_remaining < 0:
                continue

            rows.append(
                {
                    "supplier": invoice.supplier,
                    "supplier_name": invoice.supplier_name,
                    "enterprise_type": (
                        classification.enterprise_type if classification else MSME_UNCLASSIFIED
                    ),
                    "voucher_type": "Purchase Invoice",
                    "voucher_no": invoice.name,
                    "posting_date": posting_date,
                    "due_date": due_date,
                    "days_remaining": days_remaining,
                    "outstanding": flt(invoice.outstanding_amount),
                    "currency": invoice.party_account_currency or self.company_currency,
                }
            )

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
