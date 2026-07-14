# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""Voucher-wise Payment Ledger balances.

Candidate for migration to erpnext.accounts - must remain free of
india_compliance-specific imports and concepts.

Mirrors the architecture of erpnext's ``ReceivablePayableReport`` with two
deliberate differences, which are this class's reason to exist:

1. fully-settled vouchers are RETAINED (the report drops zero-outstanding rows)
2. per-settlement entries are RETAINED with their posting dates (the report
   aggregates and discards them)

Sign semantics (Payment Ledger Entry, company currency ``amount``): the
originating voucher's own entry (the "anchor", where voucher == against
voucher) is positive and allocations against it are negative, for both
Receivable and Payable account types - so a group's balance is the plain sum
of its entries. Positive balance = outstanding due, zero = fully settled,
negative = unadjusted payment / credit note.

TODO on migration: support ``amount_in_account_currency`` and account-level
grouping as parameters.
"""

import frappe
from frappe.utils import getdate

PARTY_TYPE_BY_ACCOUNT_TYPE = {"Payable": "Supplier", "Receivable": "Customer"}


class ReceivablePayableLedger:
    def __init__(self, company, account_type, report_date, party_type=None, parties=None):
        self.company = company
        self.account_type = account_type
        self.report_date = getdate(report_date)
        self.party_type = party_type or PARTY_TYPE_BY_ACCOUNT_TYPE[account_type]
        self.parties = parties
        self.ple = frappe.qb.DocType("Payment Ledger Entry")

    def run(self) -> dict[tuple, dict]:
        """Return voucher groups keyed by (voucher_type, voucher_no, party).

        Groups without an anchor (e.g. allocations of a voucher dated after
        ``report_date``) are returned with ``anchor=None`` - callers decide.
        """
        self.prepare_ple_query()
        self.add_common_filters()

        voucher_balances = self.build_voucher_balances(self.fetch_ple_entries())

        return {key: group for key, group in voucher_balances.items() if self.should_include_voucher(group)}

    def prepare_ple_query(self):
        self.query = (
            frappe.qb.from_(self.ple)
            .select(
                self.ple.against_voucher_type,
                self.ple.against_voucher_no,
                self.ple.party,
                self.ple.voucher_type,
                self.ple.voucher_no,
                self.ple.posting_date,
                self.ple.amount,
            )
            .where(self.ple.delinked == 0)
            .where(self.ple.account_type == self.account_type)
            .where(self.ple.party_type == self.party_type)
            .where(self.ple.company == self.company)
            .where(self.ple.posting_date <= self.report_date)
        )

    def add_common_filters(self):
        if self.parties:
            self.query = self.query.where(self.ple.party.isin(self.parties))

    def fetch_ple_entries(self) -> list:
        # single query; grouping happens in memory
        return self.query.run(as_dict=True)

    def build_voucher_balances(self, entries) -> dict[tuple, dict]:
        # single pass suffices: grouping is purely by the against-voucher key
        # (erpnext's report needs two passes only for its own-voucher fallbacks)
        voucher_balances = {}
        for entry in entries:
            key = (entry.against_voucher_type, entry.against_voucher_no, entry.party)
            group = voucher_balances.setdefault(key, self.build_voucher_dict(entry))
            self.update_voucher_balance(entry, group)

        return voucher_balances

    def build_voucher_dict(self, ple) -> dict:
        return frappe._dict(
            voucher_type=ple.against_voucher_type,
            voucher_no=ple.against_voucher_no,
            party=ple.party,
            anchor=None,
            settlements=[],
            balance=0,
        )

    def is_anchor(self, ple) -> bool:
        return ple.voucher_type == ple.against_voucher_type and ple.voucher_no == ple.against_voucher_no

    def update_voucher_balance(self, ple, group):
        group.balance += ple.amount

        if self.is_anchor(ple):
            group.anchor = ple
        else:
            # negated so a settlement amount is positive when it reduces the due
            group.settlements.append({"posting_date": getdate(ple.posting_date), "amount": -ple.amount})

    def should_include_voucher(self, group) -> bool:
        # settled vouchers and unadjusted credits are retained - override to narrow
        return True


def get_settlement_summary(settlements, due_date, from_date=None) -> dict:
    """Split settlement amounts into paid-on-time vs paid-late vs the due date.

    Pass ``from_date`` to count only settlements posted on or after it (e.g.
    Form-1 counts only the payments made during its half-year).
    """
    paid_on_time = paid_late = 0

    for settlement in settlements:
        posting_date = settlement["posting_date"]
        if from_date and posting_date < from_date:
            continue

        if posting_date <= due_date:
            paid_on_time += settlement["amount"]
        else:
            paid_late += settlement["amount"]

    return {"paid_on_time": paid_on_time, "paid_late": paid_late}
