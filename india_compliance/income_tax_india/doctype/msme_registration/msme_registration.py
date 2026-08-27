# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from urllib.parse import urlencode

import frappe
from frappe import _, bold
from frappe.model.document import Document, bulk_insert
from frappe.utils import format_date, get_url_to_list, getdate, random_string, today

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
        if not frappe.db.get_value(
            "Purchase Invoice", {"msme_registration": old_name, "docstatus": 1}, "name"
        ):
            return

        filters = urlencode({"msme_registration": old_name, "docstatus": 1})
        invoices = (
            f'<a href="{get_url_to_list("Purchase Invoice")}?{filters}">'
            f"{_('submitted Purchase Invoices')}</a>"
        )

        frappe.throw(_("{0} cannot be renamed as it is linked with {1}").format(bold(old_name), invoices))

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
        """Start a period no earlier than the registration itself."""
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
        """End a period no later than the cancellation itself."""
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

    def get_linked_suppliers(self) -> list[str]:
        return frappe.get_all("Supplier", filters={"msme_registration": self.name}, pluck="name")

    @frappe.whitelist()
    def mark_as_cancelled(self, cancelled_date: str, unlink_suppliers: bool = False):
        """Cancellation is a registration-level event: set the flag and date together."""
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

        if unlink_suppliers:
            self.unlink_suppliers()

        return send_updated_doc(self)

    @frappe.whitelist()
    def undo_cancellation(self):
        """
        Restore a registration cancelled by mistake.
        """
        self.check_permission("write")

        if not self.is_cancelled:
            frappe.throw(_("{0} is not cancelled").format(bold(self.name)))

        self.is_cancelled = 0
        self.cancelled_date = None
        self.save()

        return send_updated_doc(self)

    def unlink_suppliers(self):
        """
        Remove this registration from every supplier linked to it.
        """
        suppliers = self.get_linked_suppliers()
        if not suppliers:
            return

        frappe.db.set_value("Supplier", {"name": ("in", suppliers)}, "msme_registration", None)

        add_comment_to_suppliers(suppliers, self.name)


def add_comment_to_suppliers(suppliers, msme_registration):
    """
    Record the unlink on each supplier, since a bulk update leaves no version.
    """
    user = frappe.session.user
    content = _("removed MSME Registration {0}, as it was cancelled").format(msme_registration)

    comments = []
    for supplier in suppliers:
        comment = frappe.new_doc("Comment")
        comment.update(
            {
                "name": random_string(10),
                "comment_type": "Info",
                "comment_email": user,
                "comment_by": user,
                "reference_doctype": "Supplier",
                "reference_name": supplier,
                "content": content,
            }
        )
        comments.append(comment)

    bulk_insert("Comment", comments)
