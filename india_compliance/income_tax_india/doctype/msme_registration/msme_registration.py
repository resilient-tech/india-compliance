# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _, bold
from frappe.model.document import Document
from frappe.utils import format_date, getdate, today

from india_compliance.gst_india.utils import send_updated_doc
from india_compliance.income_tax_india.constants import FINANCIAL_YEAR_REGEX
from india_compliance.income_tax_india.utils.msme import (
    UDYAM_NUMBER_REGEX,
    get_financial_year_dates,
)


class MSMERegistration(Document):
    def before_naming(self):
        self.validate_udyam_number()

    def before_rename(self, old_name, new_name, merge=False):
        self.udyam_number = new_name
        self.validate_udyam_number()
        return self.udyam_number

    def validate(self):
        self.validate_udyam_number()
        self.validate_cancelled_date()
        self.validate_classifications()

    def validate_cancelled_date(self):
        if not self.is_cancelled or not self.cancelled_date:
            return

        cancelled_date = getdate(self.cancelled_date)

        if cancelled_date < getdate(self.registration_date):
            frappe.throw(_("Cancelled Date cannot be before the Registration Date"))

        if cancelled_date > getdate(today()):
            frappe.throw(_("Cancelled Date cannot be in the future"))

    def validate_udyam_number(self):
        if not self.udyam_number:
            frappe.throw(_("UDYAM Registration Number is required"))

        self.udyam_number = self.udyam_number.strip().upper()

        if not UDYAM_NUMBER_REGEX.match(self.udyam_number):
            frappe.throw(
                _(
                    "{0} is not a valid UDYAM Registration Number. Expected format: UDYAM-XX-00-0000000"
                ).format(bold(self.udyam_number)),
                title=_("Invalid UDYAM Number"),
            )

    def validate_classifications(self):
        financial_years = set()

        for row in self.classifications:
            self.validate_financial_year(row)
            self.set_period(row)
            self.validate_against_registration_date(row)
            self.validate_against_cancelled_date(row)

            if row.financial_year in financial_years:
                frappe.throw(
                    _("Row #{0}: Duplicate MSME classification for Financial Year {1}").format(
                        row.idx, bold(row.financial_year)
                    )
                )

            financial_years.add(row.financial_year)

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

    def set_period(self, row):
        if not row.financial_year:
            return

        row.from_date, row.to_date = get_financial_year_dates(row.financial_year)

    def validate_against_registration_date(self, row):
        registration_date = getdate(self.registration_date)

        if registration_date > getdate(row.to_date):
            frappe.throw(
                _("Row #{0}: Not registered in Financial Year {1}, registered on {2}").format(
                    row.idx, bold(row.financial_year), bold(format_date(registration_date))
                )
            )

        if registration_date > getdate(row.from_date):
            row.from_date = registration_date

    def validate_against_cancelled_date(self, row):
        if not self.is_cancelled or not self.cancelled_date:
            return

        cancelled_date = getdate(self.cancelled_date)

        if cancelled_date < getdate(row.from_date):
            frappe.throw(
                _("Row #{0}: Not registered in Financial Year {1}, cancelled on {2}").format(
                    row.idx, bold(row.financial_year), bold(format_date(cancelled_date))
                )
            )

        if cancelled_date < getdate(row.to_date):
            row.to_date = cancelled_date

    @frappe.whitelist()
    def mark_as_cancelled(self, cancelled_date: str):
        self.check_permission("write")

        if self.is_cancelled:
            frappe.throw(
                _("{0} was already cancelled on {1}").format(
                    bold(self.name), bold(format_date(self.cancelled_date))
                )
            )

        self.is_cancelled = 1
        self.cancelled_date = getdate(cancelled_date)
        self.save()

        return send_updated_doc(self)

    @frappe.whitelist()
    def undo_cancellation(self):
        self.check_permission("write")

        if not self.is_cancelled:
            frappe.throw(_("{0} is not cancelled").format(bold(self.name)))

        self.is_cancelled = 0
        self.cancelled_date = None
        self.save()

        return send_updated_doc(self)
