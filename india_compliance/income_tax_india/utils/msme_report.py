# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""Base class for the MSME reports.

Every MSME report answers the same three questions about a supply: was the
supplier MSME-registered when it was accepted, was that registration covered by
Section 43B(h), and when did the 45 days run out.

The registration is read from the *invoice*, never the supplier - it is a fact
about the supply. Unlinking a supplier when its registration is cancelled must
not erase its historical dues, and an invoice whose registration the user
cleared is not an MSME supply.

That pipeline lives here, bulk-loaded once per run, so a subclass only has to
supply its vouchers and its columns. The query count does not grow with the
number of rows - a subclass cannot reintroduce an N+1 by accident.

``get_msme_classification`` in ``utils.msme`` answers the same question for a
single document (a Purchase Invoice on validate). Same rule, different loading
strategy: one query per call is right there, and wrong in a report loop.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from india_compliance.income_tax_india.constants import (
    MSME_APPLICABLE_TYPES,
    TRADING_ACTIVITY,
)
from india_compliance.income_tax_india.utils.msme import (
    get_indian_fiscal_year,
    get_msme_due_date,
)
from india_compliance.utils.payment_ledger import (
    ReceivablePayableLedger,
    get_settlement_summary,
)


class MSMEReport:
    # subclass may narrow: 43B(h) excludes traders, Form-1 (MSMED Act) does not
    exclude_traders = True

    def __init__(self, filters=None):
        self.filters = frappe._dict(filters or {})

    def run(self):
        self.validate_filters()

        self.invoices = self.get_msme_invoices()
        if not self.invoices:
            return self.get_columns(), []

        self.classifications = self.get_classifications()
        self.cancellations = self.get_cancellations()

        return self.get_columns(), self.get_data()

    def validate_filters(self):
        if not self.filters.company:
            frappe.throw(_("Please select a Company"))

        self.filters.as_on_date = getdate(self.filters.as_on_date or nowdate())

    def get_msme_invoices(self) -> dict:
        """Purchase Invoices that carry an MSME registration, keyed by name.

        The registration is read from the *invoice*, not the supplier: it is what
        applied when the supply was accepted. A supplier unlinked after the
        registration was cancelled must not erase its historical dues, and an
        invoice whose registration the user cleared is not an MSME supply.

        Section 43B(h) disallows sums payable for goods supplied or services
        rendered (MSMED Act s.15), so only invoices are payables here - a Journal
        Entry crediting a supplier is not necessarily a supply.
        """
        filters = {"docstatus": 1, "msme_registration": ("is", "set"), "company": self.filters.company}
        if self.filters.supplier:
            filters["supplier"] = self.filters.supplier

        return {
            invoice.name: invoice
            for invoice in frappe.get_all(
                "Purchase Invoice",
                filters=filters,
                fields=[
                    "name",
                    "supplier",
                    "supplier_name",
                    "msme_registration",
                    "supplier.pan as pan",
                ],
            )
        }

    @property
    def suppliers(self) -> list[str]:
        return list({invoice.supplier for invoice in self.invoices.values()})

    @property
    def registrations(self) -> list[str]:
        return list({invoice.msme_registration for invoice in self.invoices.values()})

    def get_classifications(self) -> dict:
        """Classification rows keyed by (registration, financial_year)."""
        rows = frappe.get_all(
            "India MSME Classification",
            filters={"parenttype": "MSME Registration", "parent": ("in", self.registrations)},
            fields=["parent", "financial_year", "enterprise_type", "activity"],
        )
        return {(row.parent, row.financial_year): row for row in rows}

    def get_cancellations(self) -> dict:
        """Cancellation date by registration, for the ones that are cancelled."""
        rows = frappe.get_all(
            "MSME Registration",
            filters={"name": ("in", self.registrations), "is_cancelled": 1},
            fields=["name", "cancelled_date"],
        )
        return {row.name: row.cancelled_date for row in rows}

    def get_classification(self, invoice: str, posting_date):
        """Classification covering the supply this invoice was accepted for.

        None = not MSME then: unclassified for that year, or already cancelled.
        """
        registration = self.invoices[invoice].msme_registration
        posting_date = getdate(posting_date)

        if self.is_cancelled(registration, posting_date):
            return None

        return self.classifications.get((registration, get_indian_fiscal_year(posting_date)))

    def is_cancelled(self, registration: str, posting_date) -> bool:
        if registration not in self.cancellations:
            return False

        cancelled_date = self.cancellations[registration]

        # cancelled with no date on record: treated as never valid
        if not cancelled_date:
            return True

        return getdate(posting_date) > getdate(cancelled_date)

    def is_applicable(self, classification) -> bool:
        """Whether the report covers this classification."""
        if not classification:
            return False

        if classification.enterprise_type not in MSME_APPLICABLE_TYPES:
            return False

        if self.exclude_traders and classification.activity == TRADING_ACTIVITY:
            return False

        # the enterprise_type filter narrows within the above; it never widens it
        if self.filters.enterprise_type and classification.enterprise_type != self.filters.enterprise_type:
            return False

        return True

    def get_due_date(self, posting_date):
        return get_msme_due_date(posting_date)

    def get_data(self) -> list[dict]:
        raise NotImplementedError

    def get_columns(self) -> list[dict]:
        raise NotImplementedError


class MSMEPayablesReport(MSMEReport):
    """Base for the reports built on the Payment Ledger (43B(h) and Form-1).

    Both need to know *when* each rupee was paid relative to the 45-day due
    date, which ERPNext's Accounts Payable report aggregates away - hence
    ReceivablePayableLedger.

    The payable is always a Purchase Invoice - one row per supply, each with its
    own 45-day clock. An unadjusted advance is an asset, not a sum payable, so it
    is not a row; once it is allocated it reduces that invoice's outstanding and
    the disallowance follows.
    """

    # window start for the paid_within_due / paid_after_due split; Form-1 counts
    # only the payments made during its half-year
    settlement_from_date = None

    def get_payables(self) -> list[dict]:
        """Rows for the MSME invoices, with settlements from every voucher type.

        The *payable* is always a Purchase Invoice, but it may be settled by a
        Payment Entry, a Journal Entry, a credit note - the ledger picks all of
        those up as settlements against the invoice.
        """
        groups = ReceivablePayableLedger(
            company=self.filters.company,
            account_type="Payable",
            report_date=self.filters.as_on_date,
            parties=self.suppliers,
        ).run()

        records = []
        for (voucher_type, voucher_no, _party), group in groups.items():
            if voucher_type != "Purchase Invoice" or voucher_no not in self.invoices:
                continue

            if not self.is_voucher_included(group):
                continue

            posting_date = getdate(group.anchor.posting_date)
            classification = self.get_classification(voucher_no, posting_date)

            if not self.is_applicable(classification):
                continue

            records.append(self.get_voucher_row(voucher_type, voucher_no, group, classification))

        records.sort(key=lambda record: (record["supplier"], record["posting_date"]))
        return records

    def is_voucher_included(self, group) -> bool:
        # anchorless groups have no payable voucher as on date (e.g. allocations
        # of a future dated voucher)
        if not group.anchor:
            return False

        posting_date = getdate(group.anchor.posting_date)
        if posting_date > getdate(self.filters.to_date):
            return False

        return not (self.filters.from_date and posting_date < getdate(self.filters.from_date))

    def get_voucher_row(self, voucher_type, voucher_no, group, classification) -> dict:
        posting_date = getdate(group.anchor.posting_date)
        invoice = self.invoices[voucher_no]
        due_date = self.get_due_date(posting_date)

        return {
            "supplier": invoice.supplier,
            "supplier_name": invoice.supplier_name,
            "pan": invoice.pan,
            # the registration is named after the UDYAM number
            "udyam_number": invoice.msme_registration,
            "enterprise_type": classification.enterprise_type,
            "voucher_type": voucher_type,
            "voucher_no": voucher_no,
            "posting_date": posting_date,
            "financial_year": get_indian_fiscal_year(posting_date),
            "due_date": due_date,
            **self.get_due_amounts(group, due_date),
        }

    def get_due_amounts(self, group, due_date) -> dict:
        summary = get_settlement_summary(group.settlements, due_date)

        # the windowed split only differs from the full one when a start is given
        window = summary
        if self.settlement_from_date:
            window = get_settlement_summary(group.settlements, due_date, from_date=self.settlement_from_date)

        outstanding = max(flt(group.balance), 0)
        is_overdue = self.filters.as_on_date > due_date

        if outstanding <= 0:
            payment_status = "Paid Late" if summary["paid_late"] > 0 else "Paid On Time"
        elif is_overdue:
            payment_status = "Unpaid - Overdue"
        else:
            payment_status = "Within Due Date"

        return {
            "invoice_amount": flt(group.anchor.amount),
            "paid_amount": flt(summary["paid_on_time"] + summary["paid_late"]),
            "paid_within_due": flt(window["paid_on_time"]),
            "paid_after_due": flt(window["paid_late"]),
            "outstanding": outstanding,
            "outstanding_not_due": 0 if is_overdue else outstanding,
            "outstanding_overdue": outstanding if is_overdue else 0,
            # paid in-year is allowed in that year; only the unpaid overdue
            # portion is added back u/s 43B(h)
            "disallowable_amount": outstanding if is_overdue else 0,
            "payment_status": payment_status,
            "days_overdue": (self.filters.as_on_date - due_date).days if is_overdue else 0,
            "payment_date": max((s["posting_date"] for s in group.settlements), default=None),
        }
