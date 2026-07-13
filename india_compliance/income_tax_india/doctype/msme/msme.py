# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _, bold
from frappe.model.document import Document
from frappe.utils import getdate

from india_compliance.income_tax_india.constants import (
    FINANCIAL_YEAR_REGEX,
    UDYAM_NUMBER_REGEX,
)


class MSME(Document):
    def before_naming(self):
        self.validate_udyam_number()

    def validate(self):
        self.validate_udyam_number()
        self.validate_classifications()

    def validate_udyam_number(self):
        self.udyam_number = self.udyam_number.strip().upper()

        if not UDYAM_NUMBER_REGEX.match(self.udyam_number):
            frappe.throw(
                _(
                    "{0} is not a valid UDYAM Registration Number. Expected format: UDYAM-XX-00-0000000"
                ).format(bold(self.udyam_number)),
                title=_("Invalid UDYAM Number"),
            )

    def validate_classifications(self):
        seen_years = set()

        for row in self.classifications:
            self.validate_financial_year(row)

            if row.financial_year in seen_years:
                frappe.throw(
                    _("Row #{0}: Duplicate MSME classification for Financial Year {1}").format(
                        row.idx, bold(row.financial_year)
                    )
                )

            seen_years.add(row.financial_year)

    def validate_financial_year(self, row):
        financial_year = row.financial_year or ""
        start_year, _sep, end_year = financial_year.partition("-")

        if FINANCIAL_YEAR_REGEX.match(financial_year) and int(end_year) == int(start_year) + 1:
            return

        frappe.throw(
            _(
                "Row #{0}: {1} is not a valid Financial Year. Expected two consecutive years, e.g. 2024-2025"
            ).format(row.idx, bold(row.financial_year)),
            title=_("Invalid Financial Year"),
        )

    @frappe.whitelist()
    def mark_as_cancelled(self, cancelled_date: str):
        """Cancellation is a registration-level event: set the flag and date together."""
        self.check_permission("write")

        if getdate(cancelled_date) < getdate(self.registration_date or cancelled_date):
            frappe.throw(_("Cancelled Date cannot be before the Registration Date"))

        self.db_set({"is_cancelled": 1, "cancelled_date": getdate(cancelled_date)})
