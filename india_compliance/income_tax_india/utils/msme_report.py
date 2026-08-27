# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from functools import cached_property

import frappe
from frappe import _
from frappe.query_builder.functions import IfNull
from frappe.utils import flt, getdate, nowdate

from india_compliance.income_tax_india.constants import (
    MSME_APPLICABLE_TYPES,
    MSME_UNCLASSIFIED,
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

        return self.get_columns(), self.get_data()

    def validate_filters(self):
        if not self.filters.company:
            frappe.throw(_("Please select a Company"))

        self.filters.as_on_date = getdate(self.filters.as_on_date or nowdate())

    @cached_property
    def company_currency(self) -> str:
        return frappe.get_cached_value("Company", self.filters.company, "default_currency")

    @cached_property
    def invoices(self) -> dict:
        """Purchase Invoices that carry an MSME registration, keyed by name."""
        return {row.name: row for row in self.get_invoices_query().run(as_dict=True)}

    def get_invoices_query(self):
        """The invoices every MSME report reads. Subclasses narrow it further.

        A Journal Entry crediting a supplier is not necessarily a supply.
        """
        pi = frappe.qb.DocType("Purchase Invoice")
        supp = frappe.qb.DocType("Supplier")

        query = (
            frappe.qb.from_(pi)
            .left_join(supp)
            .on(supp.name == pi.supplier)
            .select(
                pi.name,
                pi.supplier,
                pi.supplier_name,
                pi.msme_registration,
                pi.posting_date,
                pi.due_date,
                pi.outstanding_amount,
                # outstanding_amount is booked in the party account's currency
                pi.party_account_currency,
                supp.pan,
            )
            .where(pi.docstatus == 1)
            .where(pi.is_return == 0)
            .where(IfNull(pi.msme_registration, "") != "")
            .where(pi.company == self.filters.company)
            .where(pi.posting_date <= (self.filters.to_date or self.filters.as_on_date))
        )

        if self.filters.from_date:
            query = query.where(pi.posting_date >= self.filters.from_date)

        if self.filters.supplier:
            query = query.where(pi.supplier == self.filters.supplier)

        return query

    @cached_property
    def classifications(self) -> dict:
        """Classification rows by registration, each with the dates it covers."""
        if not self.invoices:
            return {}

        classifications = {}
        registrations = list({invoice.msme_registration for invoice in self.invoices.values()})

        for row in frappe.get_all(
            "India MSME Classification",
            filters={"parenttype": "MSME Registration", "parent": ("in", registrations)},
            fields=[
                "parent",
                "from_date",
                "to_date",
                "enterprise_type",
                "activity",
                "not_written_agreement",
            ],
        ):
            classifications.setdefault(row.parent, []).append(row)

        return classifications

    def get_msme_status(self, registration: str, posting_date):
        """
        Classification covering the supply this registration was accepted for.
        """
        posting_date = getdate(posting_date)

        for classification in self.classifications.get(registration, []):
            if getdate(classification.from_date) <= posting_date <= getdate(classification.to_date):
                return classification

    def is_applicable(self, classification) -> bool:
        """Whether the report covers this classification."""
        if not classification:
            return not self.filters.enterprise_type

        if classification.enterprise_type not in MSME_APPLICABLE_TYPES:
            return False

        if self.exclude_traders and classification.activity == TRADING_ACTIVITY:
            return False

        # the enterprise_type filter narrows within the above; it never widens it
        if self.filters.enterprise_type and classification.enterprise_type != self.filters.enterprise_type:
            return False

        return True

    def get_due_date(self, posting_date, due_date, classification):
        """The Section 15 time limit, from inputs already bulk-loaded."""
        if not classification:
            # nothing on record says the terms were agreed in writing, so apply
            # the Act's outer limit rather than assume the stricter 15 days
            return get_msme_due_date(posting_date)

        return get_msme_due_date(posting_date, due_date, classification.not_written_agreement)

    def get_data(self) -> list[dict]:
        return []

    def get_columns(self) -> list[dict]:
        return []


class MSMEPayablesReport(MSMEReport):
    """Base for the reports built on the Payment Ledger (43B(h) and Form-1).

    Both need to know *when* each rupee was paid relative to the due date, which
    ERPNext's Accounts Payable report aggregates away - hence
    ReceivablePayableLedger.

    The payable is always a Purchase Invoice, one row per supply. An unadjusted
    advance is an asset, not a sum payable, so it is not a row; once allocated it
    reduces that invoice's outstanding and the disallowance follows.
    """

    # Form-1 counts only the payments made during its half-year
    settlement_from_date = None

    def get_payables(self) -> list[dict]:
        """Rows for the MSME invoices, settled by any voucher type the ledger holds."""
        # the ledger reads every party when given no supplier to filter by
        if not self.invoices:
            return []

        groups = ReceivablePayableLedger(
            company=self.filters.company,
            account_type="Payable",
            report_date=self.filters.as_on_date,
            parties=list({invoice.supplier for invoice in self.invoices.values()}),
        ).run()

        records = []
        for (voucher_type, voucher_no, _party), group in groups.items():
            if voucher_type != "Purchase Invoice" or voucher_no not in self.invoices:
                continue

            if not self.is_voucher_included(group):
                continue

            posting_date = getdate(group.anchor.posting_date)
            classification = self.get_msme_status(self.invoices[voucher_no].msme_registration, posting_date)

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
        due_date = self.get_due_date(posting_date, invoice.due_date, classification)

        return {
            "supplier": invoice.supplier,
            "supplier_name": invoice.supplier_name,
            "pan": invoice.pan,
            # the registration is named after its UDYAM number
            "udyam_number": invoice.msme_registration,
            "enterprise_type": classification.enterprise_type if classification else MSME_UNCLASSIFIED,
            "voucher_type": voucher_type,
            "voucher_no": voucher_no,
            "currency": self.company_currency,
            "posting_date": posting_date,
            "financial_year": get_indian_fiscal_year(posting_date),
            "due_date": due_date,
            **self.get_due_amounts(group, due_date),
        }

    def get_due_amounts(self, group, due_date) -> dict:
        summary = get_settlement_summary(group.settlements, due_date)

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
            # only the unpaid overdue portion is added back u/s 43B(h)
            "disallowable_amount": outstanding if is_overdue else 0,
            "payment_status": payment_status,
            "days_overdue": (self.filters.as_on_date - due_date).days if is_overdue else 0,
            "payment_date": max((s["posting_date"] for s in group.settlements), default=None),
        }
