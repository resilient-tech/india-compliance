# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.general_ledger import make_gl_entries, make_reverse_gl_entries
from erpnext.accounts.party import get_party_account
from erpnext.controllers.accounts_controller import AccountsController
from frappe import _
from frappe.contacts.doctype.address.address import get_address_display
from frappe.model.document import Document
from frappe.utils import flt, get_link_to_form

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.overrides.transaction import validate_gstin_status
from india_compliance.gst_india.utils import get_gst_account_gst_tax_type_map
from india_compliance.gst_india.utils.isd import (
    ISD_GST_CATEGORY,
    get_distribution_ratio,
    get_input_gst_accounts,
    get_row_itc,
    is_inter_state_distribution,
    should_distribute_expense,
    sum_row_tax_by_type,
    throw_invalid_rows,
    throw_row_table,
)


class ISDController(Document):
    """Shared functionality for ISD doctypes"""

    get_gl_dict = AccountsController.get_gl_dict
    get_value_in_transaction_currency = AccountsController.get_value_in_transaction_currency
    get_voucher_subtype = AccountsController.get_voucher_subtype
    company_currency = AccountsController.company_currency

    def is_distribution_side(self):
        return self.doctype == "ISD Distribution Invoice"

    def is_recipient_side_and_unregistered(self):
        if self.is_distribution_side():
            return False

        if not self.recipient_gstin:
            return True

        return (
            frappe.get_cached_value("Address", self.recipient_address, "gst_category") == "Unregistered"
            if self.recipient_address
            else False
        )

    def setup_precision(self):
        self._tax_precision = self.precision("tax_amount", "taxes")
        self._source_item_precision = self.precision("distributed_igst", "source_items")

    def setup_party_fields(self):
        self._party_account = None

        if not self.is_against_party:
            for field in ("party_type", "party"):
                if self.get(field):
                    self.set(field, None)
            return

        self._party_account = self.get("isd_provisional_account") or get_party_account(
            self.party_type, self.party, self.company
        )

    # ------------------------------------------------------------------ addresses
    def is_linked(self, address, link_doctype, link_name):
        return frappe.db.exists(
            "Address",
            [
                ["disabled", "=", 0],
                ["name", "=", address],
                ["Dynamic Link", "link_doctype", "=", link_doctype],
                ["Dynamic Link", "link_name", "=", link_name],
            ],
        )

    def validate_addresses(self):
        self.validate_address_links()
        self.validate_isd_party()
        self.validate_gstins()
        self.set_pos_from_address()
        self.set_address_display()

    def validate_address_links(self):
        # Each address must be enabled and linked to the entity that owns it. self.company owns the
        # distribution address on the Distribution Invoice and the recipient address on the Recipient
        # Invoice; Similar logic for recipient side.
        if self.is_distribution_side():
            company_address, company_label = self.distribution_address, _("Distribution Address")
            counterparty_address, counterparty_label = self.recipient_address, _("Recipient Address")
        else:
            company_address, company_label = self.recipient_address, _("Recipient Address")
            counterparty_address, counterparty_label = self.distribution_address, _("Distribution Address")

        counterparty_type = self.party_type if self.is_against_party else "Company"
        counterparty_name = self.party if self.is_against_party else self.company

        if company_address and not self.is_linked(company_address, "Company", self.company):
            frappe.throw(
                _(
                    "{0} {1} is not valid for this ISD distribution. Address should be enabled and linked to Company {2}."
                ).format(company_label, get_link_to_form("Address", company_address), self.company),
                title=_("Invalid Address"),
            )

        if counterparty_address and not self.is_linked(
            counterparty_address, counterparty_type, counterparty_name
        ):
            frappe.throw(
                _(
                    "{0} {1} is not valid for this ISD distribution. Address should be enabled and linked to the {2} {3}."
                ).format(
                    counterparty_label,
                    get_link_to_form("Address", counterparty_address),
                    counterparty_type,
                    counterparty_name,
                ),
                title=_("Invalid Address"),
            )

    def validate_isd_party(self):
        # The distribution address is always the Input Service Distributor; the recipient address is
        # always a non-ISD recipient.
        if (
            self.distribution_address
            and frappe.get_cached_value("Address", self.distribution_address, "gst_category")
            != ISD_GST_CATEGORY
        ):
            frappe.throw(
                _("Distribution address {0} is not registered as an Input Service Distributor (ISD).").format(
                    get_link_to_form("Address", self.distribution_address)
                )
            )

        if (
            self.recipient_address
            and frappe.get_cached_value("Address", self.recipient_address, "gst_category") == ISD_GST_CATEGORY
        ):
            frappe.throw(
                _("Recipient address {0} must not be an Input Service Distributor (ISD).").format(
                    get_link_to_form("Address", self.recipient_address)
                )
            )

    def validate_gstins(self):
        for gstin in (self.distribution_gstin, self.recipient_gstin):
            if gstin:
                validate_gstin_status(gstin, self)

        if not (self.distribution_gstin and self.recipient_gstin):
            return

        if self.distribution_gstin == self.recipient_gstin:
            frappe.throw(
                _("Credit cannot be distributed to the same GSTIN {0}.").format(
                    frappe.bold(self.distribution_gstin)
                )
            )

        if self.distribution_gstin[2:12] != self.recipient_gstin[2:12]:
            frappe.throw(
                _("PAN of Distribution GSTIN {0} and Recipient GSTIN {1} must be the same.").format(
                    frappe.bold(self.distribution_gstin), frappe.bold(self.recipient_gstin)
                )
            )

    def set_pos_from_address(self):
        def get_pos(address):
            if not address:
                return None
            state_number, state = frappe.get_cached_value(
                "Address", address, ["gst_state_number", "gst_state"]
            )
            return f"{state_number}-{state}" if state else None

        self.distribution_pos = get_pos(self.distribution_address)
        self.recipient_pos = get_pos(self.recipient_address)

    def set_address_display(self):
        self.distribution_address_display = get_address_display(self.distribution_address)
        self.recipient_address_display = get_address_display(self.recipient_address)

    # ------------------------------------------------------------------ turnover ratio

    def validate_turnover_and_ratio(self):
        branch_turnover = flt(self.branch_turnover)
        total_turnover = flt(self.total_turnover)

        if total_turnover <= 0:
            frappe.throw(_("Total Turnover must be greater than zero."))

        if branch_turnover <= 0:
            frappe.throw(_("Recipient Branch Turnover must be greater than zero."))

        if branch_turnover > total_turnover:
            frappe.throw(_("Recipient Branch Turnover cannot exceed Total Turnover."))

        # distribution_ratio is read-only / turnover-driven, so recompute it authoritatively
        self.distribution_ratio = flt(
            branch_turnover / total_turnover * 100, self.precision("distribution_ratio")
        )

    # ------------------------------------------------------------------ accounts
    def validate_accounts(self):
        """Validate that the party account and expense heads are valid for this company."""
        if self.is_against_party:
            self.validate_party_account()

        self.validate_expense_heads()

    def validate_party_account(self):
        self._validate_account(self._party_account, _("Party Account"))

        account_type, report_type = frappe.get_cached_value(
            "Account", self._party_account, ["account_type", "report_type"]
        )
        account_link = get_link_to_form("Account", self._party_account)

        if report_type != "Balance Sheet":
            frappe.throw(
                _("Party Account {0} must be a Balance Sheet account.").format(account_link),
                title=_("Invalid Account"),
            )

        expected_type = {"Customer": "Receivable", "Supplier": "Payable"}.get(self.party_type)
        if expected_type and account_type != expected_type:
            frappe.throw(
                _("Party Account {0} must be a {1} account.").format(account_link, _(expected_type)),
                title=_("Invalid Account"),
            )

    def validate_expense_heads(self):
        if not should_distribute_expense():
            return

        invalid_rows = []
        for row in self.source_items:
            try:
                self._validate_account(row.expense_head, _("Expense Head"))
            except frappe.ValidationError:
                invalid_rows.append([row.idx, row.expense_head])
        if invalid_rows:
            throw_invalid_rows(
                _("Following expense accounts are not valid for Company {0}").format(
                    frappe.bold(self.company)
                ),
                invalid_rows,
            )

    def _validate_account(self, account, label):
        "validate that the account is a non-group account belonging to this company"
        if not account:
            frappe.throw(_("{0} is required.").format(label))

        company, is_group = frappe.get_cached_value("Account", account, ["company", "is_group"])
        account_link = get_link_to_form("Account", account)

        if company != self.company:
            frappe.throw(
                _("{0} {1} does not belong to Company {2}.").format(
                    label, account_link, frappe.bold(self.company)
                )
            )
        if is_group:
            frappe.throw(_("{0} {1} cannot be a Group account.").format(label, account_link))

    # ------------------------------------------------------------------ taxes & totals
    def get_tax_amounts_by_head(self):
        """Accounts for taxes table
        Distribution side: tax types that are being reduced(credited)
        Recipient side: tax types that are being received(debited)
        """
        if self.is_distribution_side():
            return self.get_credit_by_source_head()
        return self.get_distributed_by_head()

    def get_credit_by_source_head(self):
        """Aggregate ITC types being distributed"""
        ratio = get_distribution_ratio(self)
        credit_by_type = dict.fromkeys(GST_TAX_TYPES, 0.0)
        for row in self.source_items:
            credit = get_row_itc(row, True, self._source_item_precision, ratio)
            for gst_tax_type in GST_TAX_TYPES:
                credit_by_type[gst_tax_type] += credit[gst_tax_type]
        return credit_by_type

    def get_distributed_by_head(self):
        """Aggregate ITC types being received"""
        distributed_by_type = dict.fromkeys(GST_TAX_TYPES, 0.0)
        for row in self.source_items:
            credit = get_row_itc(row, False, self._source_item_precision)
            for gst_tax_type in GST_TAX_TYPES:
                distributed_by_type[gst_tax_type] += credit[gst_tax_type]
        return distributed_by_type

    def set_taxes_and_totals(self):
        self.setup_precision()
        self.set_gst_tax_type()
        self.setup_tax_amounts()
        self.validate_gst_tax_rows()

        if self.is_recipient_side_and_unregistered():
            self.taxes = []
            self.set_tax_totals()
            self.set_provisional_values()
            return

        self.validate_missing_gst_account()
        self.set_tax_accounts()
        self.set_tax_totals()
        self.validate_gst_account_types()
        self.set_provisional_values()

    def set_gst_tax_type(self):
        if not self.taxes:
            return

        gst_tax_account_map = get_gst_account_gst_tax_type_map()
        for tax in self.taxes:
            tax.gst_tax_type = gst_tax_account_map.get(tax.account_head)

    def validate_gst_tax_rows(self):
        # only input GST accounts allowed
        accounts = get_input_gst_accounts(self.company)
        valid_accounts = {accounts.get(f"{gst_tax_type}_account") for gst_tax_type in GST_TAX_TYPES} - {None}
        invalid_rows = [
            [tax.idx, tax.account_head] for tax in self.taxes if tax.account_head not in valid_accounts
        ]
        if invalid_rows:
            throw_invalid_rows(_("Following accounts are not valid input GST accounts"), invalid_rows)

    def setup_tax_amounts(self):
        self._tax_amounts_by_head = self.get_tax_amounts_by_head()

    def validate_missing_gst_account(self):
        """Tax Types to be added to taxes table must have corresponding input GST accounts configured"""
        accounts = get_input_gst_accounts(self.company)
        missing = []
        for gst_tax_type in GST_TAX_TYPES:
            credit = flt(self._tax_amounts_by_head.get(gst_tax_type), self._source_item_precision)
            if credit and not accounts.get(f"{gst_tax_type}_account"):
                missing.append(gst_tax_type.upper())

        if missing:
            frappe.throw(
                _("No input GST account is configured for {0}. Kindly configure it in {1}.").format(
                    frappe.bold(", ".join(missing)),
                    get_link_to_form("GST Settings", "GST Settings"),
                )
            )

    def set_tax_accounts(self):
        if not self.source_items:
            self.taxes = []
            return

        accounts = get_input_gst_accounts(self.company) or {}
        existing_taxes = {tax.gst_tax_type: tax for tax in self.taxes}

        for gst_tax_type in GST_TAX_TYPES:
            account_head = accounts.get(f"{gst_tax_type}_account")
            if not account_head:
                continue

            tax = existing_taxes.get(gst_tax_type)
            if tax:
                tax.account_head = account_head
            else:
                self.append("taxes", {"account_head": account_head, "gst_tax_type": gst_tax_type})

    def set_tax_totals(self):
        """Set tax amounts and total eligible/ineligible amounts from source items"""
        totals = {"eligible": 0, "ineligible": 0}

        # expense is only distributed when enabled;
        distribute_expense = should_distribute_expense()

        for row in self.source_items:
            if not distribute_expense:
                row.distributed_expense = 0

            key = "ineligible" if row.is_ineligible_for_itc else "eligible"
            totals[key] += sum_row_tax_by_type(row, "distributed")

        for tax in self.taxes:
            calculated_amount = flt(
                self._tax_amounts_by_head.get(tax.gst_tax_type), self._source_item_precision
            )
            existing_amount = flt(tax.tax_amount, self._source_item_precision)

            # throw error on wrong tax types
            if not calculated_amount and existing_amount:
                frappe.throw(_("Invalid Tax Entry in tax table for {0}").format(tax.gst_tax_type.upper()))

            tax.tax_amount = flt(self._tax_amounts_by_head.get(tax.gst_tax_type, 0), self._tax_precision)

        # remove taxes with zero amount
        self.taxes = [tax for tax in self.taxes if tax.tax_amount]

        total_precision = self.precision("total_eligible")
        self.total_eligible = flt(totals["eligible"], total_precision)
        self.total_ineligible = flt(totals["ineligible"], total_precision)
        self.total_expense = flt(
            sum(flt(row.distributed_expense) for row in self.source_items),
            self.precision("distributed_expense"),
        )

    def validate_gst_account_types(self):
        """Receiver GST accounts must be IGST on inter-state distributions"""

        if self.is_distribution_side():
            return

        if not is_inter_state_distribution(self):
            return

        distributed_by_type = self.get_distributed_by_head()

        invalid_rows = [
            [
                gst_tax_type.upper(),
                _("{0} must be distributed as IGST for this place of supply").format(gst_tax_type.upper()),
            ]
            for gst_tax_type in ("cgst", "sgst")
            if flt(distributed_by_type.get(gst_tax_type), self._source_item_precision)
        ]
        if invalid_rows:
            throw_row_table(_("Invalid Taxes"), [_("Component"), _("Issue")], invalid_rows)

    def set_provisional_values(self):
        if not self.isd_provisional_account:
            self.isd_provisional_account = (
                self._party_account
                if self.is_against_party
                else frappe.get_cached_value("Company", self.company, "default_isd_provisional_account")
            )
        self._validate_account(self.isd_provisional_account, _("ISD Provisional Account"))

        self.isd_provisional_amount = flt(
            self.total_eligible + self.total_ineligible + self.total_expense, self._tax_precision
        )

    # ------------------------------------------------------------------ GL entries
    def on_cancel(self):
        self.ignore_linked_doctypes = ("GL Entry", "Payment Ledger Entry")
        make_reverse_gl_entries(voucher_type=self.doctype, voucher_no=self.name)

    # Code adapted from AccountsController.on_trash
    def on_trash(self):
        if not frappe.db.get_single_value("Accounts Settings", "delete_linked_ledger_entries"):
            return

        frappe.db.delete("GL Entry", {"voucher_type": self.doctype, "voucher_no": self.name})

    def make_document_gl_entries(self):
        gl_entries = self.get_gl_entries()
        if not gl_entries:
            return

        make_gl_entries(gl_entries, merge_entries=False)

    def get_gl_entries(self):
        self.setup_precision()

        # GST Expense / expense-head postings are Profit & Loss accounts that require a cost center;
        if not self.cost_center:
            self.cost_center = frappe.get_cached_value("Company", self.company, "cost_center")

        self.company_gstin = self.distribution_gstin if self.is_distribution_side() else self.recipient_gstin

        self._book_expenses = should_distribute_expense()

        # distribution side: move itc and expense from tax account to isd provisional account
        self.cr_or_dr = "credit" if self.is_distribution_side() else "debit"
        self.dr_or_cr = "debit" if self.is_distribution_side() else "credit"

        gl_entries = []
        self.add_tax_gl_entries(gl_entries)
        self.add_distributed_expense_gl_entries(gl_entries)
        self.add_ineligible_itc_gl_entries(gl_entries)

        return gl_entries

    def add_gl_entry(self, gl_entries, account, amount, side, *, row=None, party_type=None, party=None):
        """Append a single-sided GL entry."""
        amount = flt(amount, self._tax_precision)
        if not amount:
            return

        gl_entries.append(
            self.get_gl_dict(
                {
                    "account": account,
                    side: amount,
                    f"{side}_in_account_currency": amount,
                    "cost_center": (row and row.get("cost_center")) or self.cost_center,
                    "project": (row and row.get("project")) or self.project,
                    "voucher_detail_no": row and row.get("name"),
                    "party_type": party_type,
                    "party": party,
                    "remarks": _("ISD Credit Distribution"),
                },
                item=row,
            )
        )

    def get_gst_expense_account(self):
        """Get default GST Expense account set by the company"""
        account = frappe.get_cached_value("Company", self.company, "default_gst_expense_account")
        if not account:
            frappe.throw(
                _("Please set <strong>Default GST Expense Account</strong> in Company {0}").format(
                    get_link_to_form("Company", self.company)
                )
            )
        return account

    def add_provisional_gl_entry(self, gl_entries, amount, side, *, row=None):
        """Offset entry to the ISD provisional (clearing) account, carrying the party when applicable"""
        self.add_gl_entry(
            gl_entries,
            self.isd_provisional_account,
            amount,
            side,
            row=row,
            party_type=self.party_type if self.is_against_party else None,
            party=self.party if self.is_against_party else None,
        )

    def add_tax_gl_entries(self, gl_entries):
        """Tax entries from/to the ISD provisional account.

        An unregistered recipient goes to gst expense or provisional account
        """
        total = 0
        if self.is_recipient_side_and_unregistered():
            total = flt(self.total_eligible + self.total_ineligible)
            book_expense_account = (
                self.get_gst_expense_account() if self._book_expenses else self.isd_provisional_account
            )
            self.add_gl_entry(gl_entries, book_expense_account, total, self.cr_or_dr)
        else:
            for tax in self.taxes:
                self.add_gl_entry(gl_entries, tax.account_head, tax.tax_amount, self.cr_or_dr)
                total += flt(tax.tax_amount)

        self.add_provisional_gl_entry(
            gl_entries, total, self.dr_or_cr
        )  # remove the transferred amount from provisional

    def add_distributed_expense_gl_entries(self, gl_entries):
        """Distribute the pro-rata expense to each item's expense head, when enabled in GST Settings"""
        if not self._book_expenses:
            return

        total = 0
        for row in self.source_items:
            amount = flt(row.distributed_expense)
            self.add_gl_entry(gl_entries, row.expense_head, amount, self.cr_or_dr, row=row)
            total += amount

        self.add_provisional_gl_entry(
            gl_entries, total, self.dr_or_cr, row={"project": self.project, "cost_center": self.cost_center}
        )

    def add_ineligible_itc_gl_entries(self, gl_entries):
        """Correct the over-credit of ineligible ITC"""
        if self.is_recipient_side_and_unregistered():
            # values are already in the gst expense account, no reversal needed
            return

        ineligible_rows = [row for row in self.source_items if row.is_ineligible_for_itc]
        if not ineligible_rows:
            return

        tax_accounts = {tax.gst_tax_type: tax.account_head for tax in self.taxes}
        ratio = get_distribution_ratio(self)

        for row in ineligible_rows:
            # the distributor reverses its source heads
            if self.is_distribution_side():
                amounts = {
                    gst_tax_type: flt(row.get(f"total_{gst_tax_type}") * ratio, self._source_item_precision)
                    for gst_tax_type in GST_TAX_TYPES
                }
            else:
                amounts = {
                    gst_tax_type: flt(row.get(f"distributed_{gst_tax_type}"), self._source_item_precision)
                    for gst_tax_type in GST_TAX_TYPES
                }

            row_reversal_total = sum(amount for amount in amounts.values() if amount)

            # input GST accounts -> expense accounts/provisional account
            for gst_tax_type, amount in amounts.items():
                if not amount:
                    continue
                self.add_gl_entry(gl_entries, tax_accounts[gst_tax_type], amount, self.dr_or_cr, row=row)

            if not self._book_expenses:
                # -> provisional account
                self.add_provisional_gl_entry(gl_entries, row_reversal_total, self.cr_or_dr, row=row)
                continue

            # -> expense head
            self.add_gl_entry(
                gl_entries, self.get_gst_expense_account(), row_reversal_total, self.cr_or_dr, row=row
            )

            # GST Expense -> expense head
            self.add_gl_entry(gl_entries, row.expense_head, row_reversal_total, self.cr_or_dr, row=row)
            self.add_gl_entry(
                gl_entries, self.get_gst_expense_account(), row_reversal_total, self.dr_or_cr, row=row
            )
