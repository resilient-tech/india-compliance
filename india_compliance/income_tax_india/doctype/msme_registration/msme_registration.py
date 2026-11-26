# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _, bold
from frappe.model.document import Document
from frappe.utils import format_date, getdate, today

from india_compliance.gst_india.utils import commit, is_valid_pan, send_updated_doc
from india_compliance.income_tax_india.constants import FINANCIAL_YEAR_REGEX
from india_compliance.income_tax_india.utils.msme import (
    UDYAM_NUMBER_REGEX,
    get_financial_year_dates,
    get_indian_fiscal_year,
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
        self.validate_pan()
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

    def validate_pan(self):
        self.pan = (self.pan or "").strip().upper()

        if not is_valid_pan(self.pan):
            frappe.throw(_("{0} is not a valid PAN").format(bold(self.pan)), title=_("Invalid PAN"))

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


@frappe.whitelist(methods=["POST"])
def copy_to_financial_year(registrations: str | list, financial_year: str | None = None):
    frappe.has_permission("MSME Registration", "write", throw=True)

    registrations = frappe.parse_json(registrations)
    financial_year = financial_year or get_indian_fiscal_year()

    if len(registrations) > 500:
        frappe.throw(
            _("Copy supports up to 500 MSME Registrations at a time."),
            title=_("Too Many MSME Registrations"),
        )

    frappe.msgprint(_("Copying is queued in the background."), alert=True)
    frappe.enqueue(
        copy_latest_classification,
        registrations=registrations,
        financial_year=financial_year,
        queue="short",
        timeout=1000,
    )


def copy_latest_classification(registrations, financial_year):
    failed = []

    for idx, name in enumerate(registrations, 1):
        frappe.db.savepoint("copy_msme_classification")
        try:
            _copy_latest_classification(name, financial_year)
            commit()
            frappe.publish_progress(
                percent=idx / len(registrations) * 100,
                title=_("Copying MSME to {0}").format(financial_year),
                description=name,
            )

        except Exception:
            frappe.db.rollback(save_point="copy_msme_classification")
            frappe.log_error(
                _("Copying MSME category to {0} failed").format(financial_year),
                reference_doctype="MSME Registration",
                reference_name=name,
            )
            failed.append(name)

    return failed


def _copy_latest_classification(name, financial_year):
    registration = frappe.get_doc("MSME Registration", name)
    rows = sorted(registration.classifications, key=lambda row: row.financial_year)

    if not rows or rows[-1].financial_year >= financial_year:
        return

    if (
        registration.is_cancelled
        and getdate(registration.cancelled_date) < get_financial_year_dates(financial_year)[0]
    ):
        return

    registration.append(
        "classifications",
        {
            "financial_year": financial_year,
            "enterprise_type": rows[-1].enterprise_type,
            "activity": rows[-1].activity,
        },
    )
    registration.save()
