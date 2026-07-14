# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _, bold
from frappe.model.document import Document, bulk_insert
from frappe.utils import format_date, getdate, now, random_string, today

from india_compliance.income_tax_india.constants import (
    FINANCIAL_YEAR_REGEX,
    UDYAM_NUMBER_REGEX,
)


class MSMERegistration(Document):
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

            # a row is resolved by date; frappe does not run hooks on child rows,
            # so the period has to be set from here
            row.set_period()

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

    def get_linked_suppliers(self) -> list[str]:
        return frappe.get_all("Supplier", filters={"msme_registration": self.name}, pluck="name")

    @frappe.whitelist()
    def mark_as_cancelled(self, cancelled_date: str, unlink_suppliers: bool = False):
        """Cancellation is a registration-level event: set the flag and date together."""
        self.check_permission("write")
        self.validate_cancellation(cancelled_date)

        self.db_set({"is_cancelled": 1, "cancelled_date": getdate(cancelled_date)})

        if unlink_suppliers:
            self.unlink_suppliers()

    def validate_cancellation(self, cancelled_date):
        if self.is_cancelled:
            frappe.throw(
                _("{0} was already cancelled on {1}").format(
                    bold(self.name), bold(format_date(self.cancelled_date))
                )
            )

        if getdate(cancelled_date) < getdate(self.registration_date or cancelled_date):
            frappe.throw(_("Cancelled Date cannot be before the Registration Date"))

        # a future date would keep every supply until then covered by 43B(h),
        # for a supplier who is no longer an MSE
        if getdate(cancelled_date) > getdate(today()):
            frappe.throw(_("Cancelled Date cannot be in the future"))

    def unlink_suppliers(self):
        """Remove this registration from every supplier linked to it.

        Bulk updated, so the change is recorded as a Comment on each supplier
        rather than by saving each document.
        """
        suppliers = self.get_linked_suppliers()
        if not suppliers:
            return

        timestamp = now()
        frappe.db.set_value(
            "Supplier",
            {"name": ("in", suppliers)},
            {"msme_registration": None, "modified": timestamp},
            update_modified=False,
        )

        # a bulk update leaves the cached documents stale
        for supplier in suppliers:
            frappe.clear_document_cache("Supplier", supplier)

        add_comment_to_suppliers(suppliers, self.name, timestamp)


def add_comment_to_suppliers(suppliers, msme_registration, timestamp=None):
    """Record the unlink on each supplier, since a bulk update leaves no version."""
    timestamp = timestamp or now()
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
                "creation": timestamp,
                "modified": timestamp,
                "modified_by": user,
                "owner": user,
                "reference_doctype": "Supplier",
                "reference_name": supplier,
                "content": content,
            }
        )
        comments.append(comment)

    bulk_insert("Comment", comments)
