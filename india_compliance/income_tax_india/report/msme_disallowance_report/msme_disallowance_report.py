# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate

from india_compliance.income_tax_india.utils.msme_report import MSMEPayablesReport


def execute(filters: dict | None = None):
    return MSME43BHDisallowance(filters).run()


class MSME43BHDisallowance(MSMEPayablesReport):
    """Amounts payable to Micro & Small suppliers, disallowed u/s 43B(h).

    Only the unpaid overdue portion is added back: an amount paid late but within
    the same financial year is allowed in that year, so it never reaches this
    statement (it is visible in Form-1's invoice-wise view instead).
    """

    def validate_filters(self):
        super().validate_filters()

        if not (self.filters.from_date and self.filters.to_date):
            frappe.throw(_("Please select From Date and To Date"))

        if getdate(self.filters.from_date) > getdate(self.filters.to_date):
            frappe.throw(_("From Date cannot be after To Date"))

        # 43B(h) is tested at the year end: an amount unpaid on that date is
        # added back, and a payment made in a later year does not undo it. As on
        # today, that payment would zero the outstanding and the add-back would
        # silently vanish.
        self.filters.as_on_date = getdate(self.filters.to_date)

    def get_data(self):
        # only the unpaid overdue portion is added back u/s 43B(h)
        return [row for row in self.get_payables() if row["outstanding_overdue"]]

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
                "label": _("UDYAM No."),
                "fieldname": "udyam_number",
                "fieldtype": "Link",
                "options": "MSME Registration",
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
                "options": "currency",
                "width": 120,
            },
            {
                "label": _("Paid"),
                "fieldname": "paid_amount",
                "fieldtype": "Currency",
                "options": "currency",
                "width": 110,
            },
            {
                "label": _("Paid After Due (in-year)"),
                "fieldname": "paid_after_due",
                "fieldtype": "Currency",
                "options": "currency",
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
                "options": "currency",
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
                "fieldname": "outstanding_overdue",
                "fieldtype": "Currency",
                "options": "currency",
                "width": 160,
            },
        ]
