# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.party import get_party_account
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
    get_source_head_itc,
    is_inter_state_distribution,
    sum_row_tax_by_type,
    throw_invalid_rows,
    throw_row_table,
)


class ISDController(Document):
    """Shared functionality for ISD doctypes"""

    def is_distribution_side(self):
        return self.doctype == "ISD Distribution Invoice"

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
                    "{0} {1} is not valid for this ISD distribution.\n\n Address should be enabled and linked to Company {2}."
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
            credit = get_source_head_itc(row, ratio, self._source_item_precision)
            for gst_tax_type in GST_TAX_TYPES:
                credit_by_type[gst_tax_type] += credit[gst_tax_type]
        return credit_by_type

    def get_distributed_by_head(self):
        """Aggregate ITC types being received"""
        distributed_by_type = dict.fromkeys(GST_TAX_TYPES, 0.0)
        for row in self.source_items:
            for gst_tax_type in GST_TAX_TYPES:
                distributed_by_type[gst_tax_type] += flt(
                    row.get(f"distributed_{gst_tax_type}"), self._source_item_precision
                )
        return distributed_by_type

    def set_taxes_and_totals(self):
        self.setup_precision()
        self.set_gst_tax_type()
        self.setup_tax_amounts()
        self.validate_gst_tax_rows()
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
        # only input GST accounts for tax types that actually carry an amount may appear
        accounts = get_input_gst_accounts(self.company)
        valid_accounts = {
            accounts.get(f"{gst_tax_type}_account")
            for gst_tax_type in GST_TAX_TYPES
            if flt(self._tax_amounts_by_head.get(gst_tax_type), self._source_item_precision)
        } - {None}
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
            # Book only the heads that actually carry an amount.
            if not flt(self._tax_amounts_by_head.get(gst_tax_type), self._source_item_precision):
                continue

            account_head = accounts.get(f"{gst_tax_type}_account")
            if not account_head:
                continue

            tax = existing_taxes.get(gst_tax_type)
            if tax:
                tax.account_head = account_head
            else:
                self.append("taxes", {"account_head": account_head, "gst_tax_type": gst_tax_type})

    def set_tax_totals(self):
        """Set tax amounts and total eligible/ineligible amounts."""
        totals = {"eligible": 0, "ineligible": 0}

        for row in self.source_items:
            key = "ineligible" if row.is_ineligible_for_itc else "eligible"
            totals[key] += sum_row_tax_by_type(row, "distributed")

        for tax in self.taxes:
            tax.tax_amount = flt(self._tax_amounts_by_head.get(tax.gst_tax_type, 0), self._tax_precision)

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
            for gst_tax_type in GST_TAX_TYPES
            if gst_tax_type != "igst"
            and flt(distributed_by_type.get(gst_tax_type), self._source_item_precision)
        ]
        if invalid_rows:
            throw_row_table(_("Invalid Taxes"), [_("Component"), _("Issue")], invalid_rows)

    def set_provisional_values(self):
        self.isd_provisional_amount = flt(sum(flt(tax.tax_amount) for tax in self.taxes), self._tax_precision)

        if self.isd_provisional_account:
            return
        elif self.is_against_party:
            self.isd_provisional_account = self._party_account
        else:
            self.isd_provisional_account = frappe.get_cached_value(
                "Company", self.company, "default_isd_provisional_account"
            )
