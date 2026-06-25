# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from collections import defaultdict
from functools import reduce
from operator import add

import frappe
from erpnext import get_default_cost_center
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
    get_accounting_dimensions,
)
from erpnext.accounts.general_ledger import make_gl_entries, make_reverse_gl_entries
from erpnext.accounts.party import get_party_account
from erpnext.controllers.accounts_controller import AccountsController
from frappe import _
from frappe.contacts.doctype.address.address import get_address_display
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.model.meta import get_field_precision
from frappe.query_builder.functions import Sum
from frappe.utils import cint, flt, get_link_to_form, getdate

from india_compliance.gst_india.constants import (
    GST_TAX_TYPES,
)
from india_compliance.gst_india.overrides.transaction import validate_gstin_status
from india_compliance.gst_india.utils import (
    get_gst_account_gst_tax_type_map,
    get_gst_accounts_by_type,
    validate_invoice_number,
)
from india_compliance.gst_india.utils.isd import (
    CREDIT_FLOW,
    ISD_GST_CATEGORY,
    _get_purchase_invoices_distribution_summary,
    is_inter_state_distribution,
    sum_row_tax_by_type,
    throw_invalid_rows,
    throw_row_table,
)


class ISDInvoice(Document):
    get_gl_dict = AccountsController.get_gl_dict
    get_value_in_transaction_currency = AccountsController.get_value_in_transaction_currency
    get_voucher_subtype = AccountsController.get_voucher_subtype
    company_currency = AccountsController.company_currency
    validate_account_currency = AccountsController.validate_account_currency

    def validate(self):
        self.reset_fields_if_party_not_set()
        validate_invoice_number(self)
        self.validate_addresses()
        self.set_taxes_and_totals()
        self.validate_accounts()
        self.validate_internal_invoice()

    def validate_addresses(self):
        self.validate_address_links()
        self.validate_isd_party()
        self.validate_gstins()

        self.set_pos_from_address()
        self.set_address_display()

    def validate_internal_invoice(self):
        if self.is_external_invoice:
            return

        self.validate_inter_company_transaction()
        self.validate_purchase_invoices()
        self.validate_distribution_limits()

    def validate_accounts(self):
        # the party leg of the GL booking uses one of these accounts depending on the recipient
        if self.is_against_party:
            self.validate_party_account()
        elif not self.party_gstin:
            self.validate_expense_account()

    def validate_party_account(self):
        if not self.party_account:
            self.party_account = get_party_account(self.party_type, self.party, self.company)

        self._validate_account("party_account", _("Party Account"))

        account_type, report_type = frappe.get_cached_value(
            "Account", self.party_account, ["account_type", "report_type"]
        )
        account_link = get_link_to_form("Account", self.party_account)

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

    def validate_expense_account(self):
        if not self.expense_account:
            self.expense_account = frappe.get_cached_value(
                "Company", self.company, "default_gst_expense_account"
            )

        self._validate_account("expense_account", _("GST Expense Account"))

    def _validate_account(self, fieldname, label):
        account = self.get(fieldname)
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

    def set_taxes_and_totals(self):
        self.setup_precision()
        self.set_gst_tax_type()
        self.validate_gst_tax_rows()
        self.validate_missing_gst_account()
        self.set_distributed_taxes()
        self.set_distribution_totals()
        self.validate_gst_account_types()

    def setup_precision(self):
        self._tax_precision = self.precision("tax_amount", "taxes")
        self._source_item_precision = self.precision("distributed_igst", "source_invoices")

    def set_gst_tax_type(self):
        if not self.taxes:
            return

        gst_tax_account_map = get_gst_account_gst_tax_type_map()
        for tax in self.taxes:
            tax.gst_tax_type = gst_tax_account_map.get(tax.account_head)

    def set_distributed_taxes(self):
        if not self.source_invoices:
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

    def set_distribution_totals(self):
        totals = {"eligible": 0, "ineligible": 0}
        distributed_by_type = dict.fromkeys(GST_TAX_TYPES, 0)

        for row in self.source_invoices:
            key = "ineligible" if row.is_ineligible_for_itc else "eligible"
            totals[key] += sum_row_tax_by_type(row, "distributed")
            for gst_tax_type in GST_TAX_TYPES:
                distributed_by_type[gst_tax_type] += flt(
                    row.get(f"distributed_{gst_tax_type}"), self._source_item_precision
                )

        for tax in self.taxes:
            tax.tax_amount = flt(distributed_by_type.get(tax.gst_tax_type, 0), self._tax_precision)

        self.taxes = [tax for tax in self.taxes if tax.tax_amount]

        total_precision = self.precision("total_eligible")
        self.total_eligible = flt(totals["eligible"], total_precision)
        self.total_ineligible = flt(totals["ineligible"], total_precision)

    def set_pos_from_address(self):
        def get_pos(address):
            if not address:
                return None
            state_number, state = frappe.get_cached_value(
                "Address", address, ["gst_state_number", "gst_state"]
            )
            return f"{state_number}-{state}" if state else None

        self.company_pos = get_pos(self.company_address)
        self.party_pos = get_pos(self.party_address)

    def set_address_display(self):
        self.company_address_display = get_address_display(self.company_address)
        self.party_address_display = get_address_display(self.party_address)

    def reset_fields_if_party_not_set(self):
        if self.is_against_party:
            return

        for field in ("party_type", "party", "credit_flow", "party_account"):
            if self.get(field):
                self.set(field, None)

    def validate_isd_party(self):
        is_company_isd = not self.is_against_party or self.credit_flow == CREDIT_FLOW.DISTRIBUTION
        isd_field = "company_address" if is_company_isd else "party_address"
        recipient_field = "party_address" if is_company_isd else "company_address"

        isd_address = self.get(isd_field)
        if (
            isd_address
            and frappe.get_cached_value("Address", isd_address, "gst_category") != ISD_GST_CATEGORY
        ):
            frappe.throw(
                _("{0} address {1} is not registered as an Input Service Distributor (ISD).").format(
                    _("Company") if is_company_isd else _("Party"),
                    get_link_to_form("Address", isd_address),
                )
            )

        recipient_address = self.get(recipient_field)
        if (
            recipient_address
            and frappe.get_cached_value("Address", recipient_address, "gst_category") == ISD_GST_CATEGORY
        ):
            frappe.throw(
                _("{0} address {1} must not be an Input Service Distributor (ISD).").format(
                    _("Party") if is_company_isd else _("Company"),
                    get_link_to_form("Address", recipient_address),
                )
            )

    def validate_address_links(self):
        # the address must be enabled and linked to the company / party
        common_filters = [["disabled", "=", 0]]
        company_filters = [
            *common_filters,
            ["name", "=", self.company_address],
            ["Dynamic Link", "link_doctype", "=", "Company"],
            ["Dynamic Link", "link_name", "=", self.company],
        ]

        party_type = "Company" if not self.is_against_party else self.party_type
        party = self.company if not self.is_against_party else self.party
        party_filters = [
            *common_filters,
            ["name", "=", self.party_address],
            ["Dynamic Link", "link_doctype", "=", party_type],
            ["Dynamic Link", "link_name", "=", party],
        ]

        if self.company_address and not frappe.db.exists("Address", company_filters):
            frappe.throw(
                _("Company Address {0} is not valid for this ISD distribution.").format(
                    get_link_to_form("Address", self.company_address)
                )
            )

        if self.party_address and not frappe.db.exists("Address", party_filters):
            frappe.throw(
                _("Party Address {0} is not valid for this ISD distribution.").format(
                    get_link_to_form("Address", self.party_address)
                )
            )

    def validate_gstins(self):
        for gstin in (self.company_gstin, self.party_gstin):
            if gstin:
                validate_gstin_status(gstin, self)

        if not (self.company_gstin and self.party_gstin):
            return

        if self.company_gstin == self.party_gstin:
            frappe.throw(
                _("Credit cannot be distributed to the same GSTIN {0}.").format(
                    frappe.bold(self.company_gstin)
                )
            )

        if self.company_gstin[2:12] != self.party_gstin[2:12]:
            frappe.throw(
                _("PAN of Company GSTIN {0} and Party GSTIN {1} must be the same.").format(
                    frappe.bold(self.company_gstin), frappe.bold(self.party_gstin)
                )
            )

    def validate_gst_tax_rows(self):
        # only the company's input GST accounts may appear in the taxes table
        accounts = get_input_gst_accounts(self.company)
        input_accounts = {accounts.get(f"{gst_tax_type}_account") for gst_tax_type in GST_TAX_TYPES} - {None}
        invalid_rows = [
            [tax.idx, tax.account_head] for tax in self.taxes if tax.account_head not in input_accounts
        ]
        throw_invalid_rows(_("Following accounts are not input GST accounts"), invalid_rows)

    def validate_missing_gst_account(self):
        """A GST type carrying a distributed amount needs a configured input GST account to book it."""
        accounts = get_input_gst_accounts(self.company)
        missing = []
        for gst_tax_type in GST_TAX_TYPES:
            distributed = flt(
                sum(row.get(f"distributed_{gst_tax_type}") or 0 for row in self.source_invoices),
                self._source_item_precision,
            )
            if distributed and not accounts.get(f"{gst_tax_type}_account"):
                missing.append(gst_tax_type.upper())

        if missing:
            frappe.throw(
                _("No input GST account is configured for {0}. Kindly configure it in {1}.").format(
                    frappe.bold(", ".join(missing)),
                    get_link_to_form("GST Settings", "GST Settings"),
                )
            )

    def validate_gst_account_types(self):
        """Inter-state distribution collapses all credit to IGST, so CGST/SGST are forbidden.
        Intra-state keeps each credit's type (IGST credit stays IGST, CGST/SGST stay CGST/SGST
        per Rule 39(1)(e), (f)), so no tax type is forbidden."""
        forbidden = ("cgst", "sgst") if is_inter_state_distribution(self) else ()
        invalid_rows = [
            [
                str(tax.idx),
                tax.account_head,
                _("{0} cannot be distributed for this place of supply").format(tax.gst_tax_type.upper()),
            ]
            for tax in self.taxes
            if tax.tax_amount and tax.gst_tax_type in forbidden
        ]
        throw_row_table(_("Invalid Taxes"), [_("Row"), _("Account"), _("Issue")], invalid_rows)

    def validate_purchase_invoices(self):
        self._pi_data = {
            row.name: row
            for row in frappe.db.get_all(
                "Purchase Invoice",
                filters={"name": ("in", self.get_purchase_invoice_names())},
                fields=["name", "docstatus", "is_isd_applicable", "posting_date", "company", "company_gstin"],
            )
        }

        self._validate_duplication()
        self._validate_purchase_invoices_submitted()
        self._validate_purchase_invoices_isd_applicable()
        self._validate_source_invoice_dates()
        self._validate_purchase_invoice_company()
        self._validate_source_invoices_with_inter_company_reference()

    def get_purchase_invoice_names(self):
        return list({row.purchase_invoice for row in self.source_invoices if row.purchase_invoice})

    def _validate_duplication(self):
        seen = set()
        invalid_rows = []
        for row in self.source_invoices:
            key = (row.purchase_invoice, cint(row.is_ineligible_for_itc))
            if key in seen:
                invalid_rows.append([row.idx, row.purchase_invoice])
            seen.add(key)

        throw_invalid_rows(_("Following purchase invoices are added more than once"), invalid_rows)

    def _validate_purchase_invoices_submitted(self):
        invalid_rows = []
        for row in self.source_invoices:
            pi = self._pi_data.get(row.purchase_invoice)
            if not pi or pi.docstatus != 1:
                invalid_rows.append([row.idx, row.purchase_invoice])

        throw_invalid_rows(_("Following purchase invoices are not submitted"), invalid_rows)

    def _validate_purchase_invoices_isd_applicable(self):
        invalid_rows = []
        for row in self.source_invoices:
            pi = self._pi_data.get(row.purchase_invoice)
            if pi and not pi.is_isd_applicable:
                invalid_rows.append([row.idx, row.purchase_invoice])

        throw_invalid_rows(_("Following purchase invoices are not ISD applicable"), invalid_rows)

    def _validate_source_invoice_dates(self):
        # Posting Date should be before or on the same date as the Purchase Invoice GSTR-6 Rule 39
        invalid_rows = []
        for row in self.source_invoices:
            pi = self._pi_data.get(row.purchase_invoice)
            if pi and getdate(pi.posting_date) > getdate(self.posting_date):
                invalid_rows.append([row.idx, row.purchase_invoice])

        throw_invalid_rows(
            _("Posting date of following purchase invoices is after this ISD invoice"),
            invalid_rows,
        )

    def _validate_purchase_invoice_company(self):
        # in the receipt flow the source invoices belong to the distributing branch, not this company
        if self.credit_flow == CREDIT_FLOW.RECEIPT:
            return

        # company and GSTIN mismatches are distinct issues, so they share a table with an Issue column
        invalid_rows = []
        for row in self.source_invoices:
            pi = self._pi_data.get(row.purchase_invoice)
            if pi.company != self.company:
                invalid_rows.append([str(row.idx), row.purchase_invoice, _("Belongs to a different company")])
            elif pi.company_gstin != self.company_gstin:
                invalid_rows.append(
                    [str(row.idx), row.purchase_invoice, _("Booked under a different Company GSTIN")]
                )

        throw_row_table(
            _("Invalid Source Invoices"), [_("Row"), _("Purchase Invoice"), _("Issue")], invalid_rows
        )

    def validate_inter_company_transaction(self):
        if not self.is_against_party or not self.party:
            return

        # check if your party internal
        internal = "is_internal_supplier" if self.party_type == "Supplier" else "is_internal_customer"
        if not frappe.db.exists(self.party_type, {"name": self.party, internal: 1}):
            return

        allowed_companies = frappe.get_all(
            "Allowed To Transact With",
            filters={"parenttype": self.party_type, "parent": self.party},
            pluck="company",
        )
        if self.company not in allowed_companies:
            frappe.throw(
                _(
                    "{0} {1} is not allowed to transact with Company {2}. Add the company in"
                    " 'Allowed To Transact With' section of the {0} record."
                ).format(self.party_type, self.party, self.company)
            )

    def validate_distribution_limits(self):
        """Distributed amounts must not exceed the amount available per (purchase invoice, eligibility)"""
        if self.is_credit_receipt():
            return

        # single source of truth for both totals (authoritative from the PI) and amounts
        # already distributed by other submitted ISD invoices
        summary_map = {
            (row.purchase_invoice, cint(row.is_ineligible_for_itc)): row
            for row in _get_purchase_invoices_distribution_summary(self.get_purchase_invoice_names())
        }
        self._already_distributed_map = {
            key: flt(row.distributed_tax, self._source_item_precision) for key, row in summary_map.items()
        }

        invalid_distributions = []
        for row in self.source_invoices:
            key = (row.purchase_invoice, cint(row.is_ineligible_for_itc))
            pi_row = summary_map.get(key)
            if not pi_row:
                continue

            # totals are read-only and set directly from the purchase invoice
            for t in GST_TAX_TYPES:
                row.set(f"total_{t}", flt(pi_row[f"total_{t}"], self._source_item_precision))

            prior = self._already_distributed_map[key]
            distributed = flt(sum_row_tax_by_type(row, "distributed"), self._source_item_precision)

            if self.is_credit_note and (prior + distributed < 0):
                invalid_distributions.append((*key, prior, abs(distributed)))
            else:
                available = flt(pi_row.available_tax, self._source_item_precision)
                if distributed > available:
                    invalid_distributions.append((*key, available, distributed))

        if invalid_distributions:
            self.throw_invalid_distributions(invalid_distributions)

    def is_credit_receipt(self):
        return bool(self.is_against_party and self.credit_flow == CREDIT_FLOW.RECEIPT)

    def throw_invalid_distributions(self, invalid_distributions):
        if self.is_credit_note:
            title, left_label, right_label = (
                _("Invalid Credit Note Reversal"),
                _("Originally Distributed"),
                _("Reversing"),
            )
        else:
            title, left_label, right_label = _("Invalid Tax Distribution"), _("Available"), _("Distributed")

        precision = self._source_item_precision
        rows = [
            [
                purchase_invoice,
                _("Ineligible") if is_ineligible else _("Eligible"),
                f"{flt(available, precision):.{precision}f}",
                f"{flt(distributed, precision):.{precision}f}",
            ]
            for purchase_invoice, is_ineligible, available, distributed in invalid_distributions
        ]
        throw_row_table(title, [_("Purchase Invoice"), _("Type"), left_label, right_label], rows)

    def on_submit(self):
        make_gl_entries(self.get_gl_entries(), merge_entries=False)
        self._sync_purchase_invoice_distribution()

    def on_cancel(self):
        self.ignore_linked_doctypes = ("GL Entry", "Payment Ledger Entry")
        make_reverse_gl_entries(voucher_type=self.doctype, voucher_no=self.name)
        self._sync_purchase_invoice_distribution()

    def get_gl_entries(self):
        gl_entries = []
        self.make_company_gl_entries(gl_entries)
        self.make_recipient_gl_entries(gl_entries)
        return gl_entries

    def make_company_gl_entries(self, gl_entries):
        # input GST of the distributing company: credited as credit leaves it (debited on receipt/reversal)
        dr_or_cr = "debit" if self.is_credit_receipt() else "credit"
        for tax in self.taxes:
            gl_entries.append(
                self._gst_gl_dict(tax.account_head, dr_or_cr, tax.tax_amount, self.company_gstin)
            )

    def make_recipient_gl_entries(self, gl_entries):
        # the receiving side always books the opposite leg of the company entries
        dr_or_cr = "credit" if self.is_credit_receipt() else "debit"

        # registered branch of the same company: mirror each input GST account under its GSTIN
        if not self.is_against_party and self.party_gstin:
            for tax in self.taxes:
                gl_entries.append(
                    self._gst_gl_dict(tax.account_head, dr_or_cr, tax.tax_amount, self.party_gstin)
                )
            return

        total_tax = flt(sum(tax.tax_amount for tax in self.taxes), self.precision("tax_amount", "taxes"))

        # unregistered branch of the same company: the credit becomes GST Expense (no recipient GSTIN)
        if not self.is_against_party:
            gl_entries.append(self._gst_gl_dict(self.expense_account, dr_or_cr, total_tax, None))
            return

        # distribution to / receipt from an external party
        gl_entries.append(
            self._gst_gl_dict(
                self.party_account,
                dr_or_cr,
                total_tax,
                self.party_gstin,
                party_type=self.party_type,
                party=self.party,
            )
        )

    def _gst_gl_dict(self, account, dr_or_cr, amount, company_gstin, **attributes):
        gl_dict = {
            "account": account,
            "debit": 0,
            "credit": 0,
            dr_or_cr: amount,  # "debit" or "credit"
            "cost_center": self.cost_center or get_default_cost_center(self.company),
            **attributes,
        }
        if company_gstin:
            gl_dict["company_gstin"] = company_gstin

        return self.get_gl_dict(gl_dict)

    def _sync_purchase_invoice_distribution(self):
        # recipient ISD invoices do not affect the PI's of distribution company
        if self.is_credit_receipt():
            return

        pi_names = self.get_purchase_invoice_names()
        if not pi_names:
            return

        source_item_precision = self.precision("distributed_igst", "source_invoices")
        total_tax_map = defaultdict(float)
        distributed_map = defaultdict(float)
        for row in _get_purchase_invoices_distribution_summary(pi_names):
            total_tax_map[row.purchase_invoice] += flt(row.total_tax, source_item_precision)
            distributed_map[row.purchase_invoice] += flt(row.distributed_tax, source_item_precision)

        doc_updates = {}
        _percentage_precision = get_field_precision(
            frappe.get_meta("Purchase Invoice").get_field("isd_credit_distributed_percent")
        )
        for name in pi_names:
            total_tax = total_tax_map.get(name, 0)
            total_distributed = distributed_map.get(name, 0)
            raw_percent = total_distributed / total_tax * 100 if total_tax else 0
            percent = flt(raw_percent, _percentage_precision)
            # rounding can read 100% while slightly under-distributed; never overstate full distribution
            if percent >= 100 and raw_percent < 100:
                percent = flt(100 - 10**-_percentage_precision, _percentage_precision)
            doc_updates[name] = {"isd_credit_distributed_percent": percent}

        frappe.db.bulk_update("Purchase Invoice", doc_updates, update_modified=False)

    @frappe.whitelist()
    def get_purchase_invoices(self, purchase_invoices: list, distribution_ratio: float = 0.0):
        if not purchase_invoices:
            frappe.msgprint(_("No Purchase Invoices selected"))
            return []

        frappe.has_permission("Purchase Invoice", "read", throw=True)
        frappe.has_permission("ISD Invoice", "write", throw=True)

        # existing non-empty items
        existing_items = [
            (item.purchase_invoice, cint(item.is_ineligible_for_itc))
            for item in self.source_invoices
            if item.purchase_invoice
        ]
        items_to_add = get_source_invoices_from_purchase_invoices(purchase_invoices)

        if not existing_items:
            self.source_invoices = []

        for item in items_to_add:
            if (item.purchase_invoice, cint(item.is_ineligible_for_itc)) not in existing_items:
                self.append("source_invoices", {**item, "distribution_ratio": distribution_ratio})

    def _validate_source_invoices_with_inter_company_reference(self):
        if not (
            self.is_against_party
            and self.credit_flow == CREDIT_FLOW.RECEIPT
            and self.inter_company_invoice_reference
        ):
            return

        tax_fields = [f"{prefix}_{t}" for prefix in ("total", "distributed") for t in GST_TAX_TYPES]
        reference_items = frappe.get_all(
            "ISD Invoice Source Item",
            filters={"parent": self.inter_company_invoice_reference},
            fields=["purchase_invoice", "is_ineligible_for_itc", *tax_fields],
        )

        def row_keys(items):
            return {
                (
                    row.purchase_invoice,
                    cint(row.is_ineligible_for_itc),
                    *(flt(row.get(f)) for f in tax_fields),
                )
                for row in items
            }

        # source invoices must be identical to the inter company reference
        mismatched_invoices = {key[0] for key in row_keys(reference_items) ^ row_keys(self.source_invoices)}
        if mismatched_invoices:
            frappe.throw(
                _("Following Purchase Invoices do not match the inter company ISD Invoice: {0}").format(
                    ", ".join(mismatched_invoices)
                )
            )


@frappe.whitelist()
def get_source_invoices_from_purchase_invoices(purchase_invoices: list | str):
    frappe.has_permission("Purchase Invoice", "read", throw=True)
    frappe.has_permission("ISD Invoice", "create", throw=True)

    if isinstance(purchase_invoices, str):
        purchase_invoices = frappe.parse_json(purchase_invoices)

    pi_item = frappe.qb.DocType("Purchase Invoice Item")
    return (
        frappe.qb.from_(pi_item)
        .where(pi_item.docstatus == 1)
        .where(pi_item.parent.isin(purchase_invoices))
        .select(
            pi_item.parent.as_("purchase_invoice"),
            pi_item.is_ineligible_for_itc,
            *[Sum(getattr(pi_item, f"{t}_amount")).as_(f"total_{t}") for t in GST_TAX_TYPES],
        )
        .groupby(pi_item.parent, pi_item.is_ineligible_for_itc)
        .having(Sum(reduce(add, (pi_item[f"{t}_amount"] for t in GST_TAX_TYPES))) > 0)
        .run(as_dict=True)
    )


def _resolve_credit_flow(doc):
    return CREDIT_FLOW.DISTRIBUTION if doc.is_against_party else None


def _resolve_party_type(doc):
    if not doc.is_against_party:
        return None
    return "Customer" if doc.credit_flow == CREDIT_FLOW.DISTRIBUTION else "Supplier"


def _resolve_party(doc):
    if not (doc.is_against_party and doc.party_type):
        return None

    internal_field = "is_internal_customer" if doc.party_type == "Customer" else "is_internal_supplier"
    parties = frappe.get_list(
        doc.party_type, filters={internal_field: 1, "disabled": 0}, pluck="name", limit=1
    )
    return parties[0] if parties else None


PARTY_RESOLVERS = {
    "is_against_party": lambda doc: doc.is_against_party,
    "credit_flow": _resolve_credit_flow,
    "party_type": _resolve_party_type,
    "party": _resolve_party,
}


def _resolve_party_account(doc):
    if not (doc.is_against_party and doc.company and doc.party_type and doc.party):
        return None
    return get_party_account(doc.party_type, doc.party, doc.company)


def _get_autofill_addresses(doc):
    if not doc.company:
        return None, None

    def fetch_address(link_doctype, link_name, *, exclude_isd=False):
        results = frappe.get_list(
            "Address",
            filters=[
                ["disabled", "=", 0],
                ["Dynamic Link", "link_doctype", "=", link_doctype],
                ["Dynamic Link", "link_name", "=", link_name],
                ["gst_category", "!=" if exclude_isd else "=", ISD_GST_CATEGORY],
            ],
            pluck="name",
            order_by="is_primary_address DESC",
            limit=1,
        )
        return results[0] if results else None

    if not doc.is_against_party:
        return (
            fetch_address("Company", doc.company),
            fetch_address("Company", doc.company, exclude_isd=True),
        )

    if not (doc.party_type and doc.party):
        return None, None

    is_distribution = doc.credit_flow == CREDIT_FLOW.DISTRIBUTION
    return (
        fetch_address("Company", doc.company, exclude_isd=not is_distribution),
        fetch_address(doc.party_type, doc.party, exclude_isd=is_distribution),
    )


@frappe.whitelist()
def get_isd_autofill_values(changed_field: str, doc: str | dict):
    PARTY_CHAIN = ("company", "is_against_party", "credit_flow", "party_type", "party")

    doc = frappe._dict(frappe.parse_json(doc))
    doc.is_against_party = cint(doc.is_against_party)

    result = frappe._dict()

    if changed_field in PARTY_CHAIN:
        downstream = PARTY_CHAIN[PARTY_CHAIN.index(changed_field) + 1 :]
        for field in downstream:
            doc[field] = result[field] = PARTY_RESOLVERS[field](doc)

    result.company_address, result.party_address = _get_autofill_addresses(doc)
    result.party_account = _resolve_party_account(doc)

    return result


@frappe.whitelist()
def get_input_gst_accounts(company: str):
    return get_gst_accounts_by_type(company, "Input")


def _map_isd_invoice(source_name, target_doc, field_map, post_process, map_accounting_dimensions=False):
    item_fields = [
        "purchase_invoice",
        "is_ineligible_for_itc",
        "distribution_ratio",
        "distribution_amount",
        *[f"total_{tax_type}" for tax_type in GST_TAX_TYPES],
        *[f"distributed_{tax_type}" for tax_type in GST_TAX_TYPES],
    ]

    mapped_field_map = {**field_map}
    if map_accounting_dimensions:
        meta = frappe.get_meta("ISD Invoice")
        for fieldname in get_accounting_dimensions(as_list=True):
            if meta.has_field(fieldname):
                mapped_field_map[fieldname] = fieldname

    return get_mapped_doc(
        "ISD Invoice",
        source_name,
        {
            "ISD Invoice": {
                "doctype": "ISD Invoice",
                "validation": {"docstatus": ["=", 1]},
                "field_map": mapped_field_map,
            },
            "ISD Invoice Source Item": {
                "doctype": "ISD Invoice Source Item",
                "field_map": item_fields,
            },
            "ISD Invoice Tax Item": {"doctype": "ISD Invoice Tax Item", "ignore": True},
        },
        target_doc,
        post_process,
    )


@frappe.whitelist()
def create_inter_company_invoice(source_name: str, target_doc: str | None = None):
    frappe.has_permission("ISD Invoice", "write", throw=True)

    def post_process(source, target):
        # similar logic to autofill
        new_direction = (
            CREDIT_FLOW.RECEIPT
            if source.credit_flow == CREDIT_FLOW.DISTRIBUTION
            else CREDIT_FLOW.DISTRIBUTION
        )
        new_party_type = "Customer" if new_direction == CREDIT_FLOW.DISTRIBUTION else "Supplier"
        new_company = frappe.get_value(source.party_type, source.party, "represents_company")
        internal_field = "is_internal_customer" if new_party_type == "Customer" else "is_internal_supplier"
        new_party_name = frappe.get_value(
            new_party_type, {"represents_company": source.company, internal_field: 1}, "name"
        )

        # custom logic for address - match address based on gstin
        company_address = frappe.get_value(
            "Address",
            filters=[
                ["Dynamic Link", "link_name", "=", new_company],
                ["Dynamic Link", "link_doctype", "=", "Company"],
                ["Address", "gstin", "=", source.party_gstin],
            ],
            order_by="is_primary_address DESC",
            pluck="name",
        )

        party_address = frappe.get_value(
            "Address",
            filters=[
                ["Dynamic Link", "link_name", "=", new_party_name],
                ["Dynamic Link", "link_doctype", "=", new_party_type],
                ["Address", "gstin", "=", source.company_gstin],
            ],
            order_by="is_primary_address DESC",
            pluck="name",
        )

        party_account = None
        if new_party_name and new_company:
            party_account = get_party_account(new_party_type, new_party_name, new_company)

        credit_note_against = None
        if source.credit_note_against:
            credit_note_against = frappe.db.get_value(
                "ISD Invoice", source.credit_note_against, "inter_company_invoice_reference"
            )

        target.update(
            {
                "is_against_party": 1,
                "credit_flow": new_direction,
                "party_type": new_party_type,
                "company": new_company,
                "party": new_party_name,
                "inter_company_invoice_reference": source.name,
                "company_address": company_address,
                "party_address": party_address,
                "party_account": party_account,
                "credit_note_against": credit_note_against,
            }
        )

        if any(
            v is None for v in [new_company, new_party_name, company_address, party_address, party_account]
        ):
            frappe.msgprint(
                _("Invoice created with missing field values."),
                alert=True,
            )

    return _map_isd_invoice(
        source_name,
        target_doc,
        {
            "naming_series": "naming_series",
            "is_credit_note": "is_credit_note",
            "posting_date": "posting_date",
            "default_distribution_ratio": "default_distribution_ratio",
        },
        post_process,
    )


@frappe.whitelist()
def make_credit_note(source_name: str, target_doc: str | None = None):
    frappe.has_permission("ISD Invoice", "write", throw=True)

    distributed_fields = [f"distributed_{tax_type}" for tax_type in GST_TAX_TYPES]
    tax_precision = get_field_precision(
        frappe.get_meta("ISD Invoice Source Item").get_field("distributed_igst")
    )

    def post_process(source, target):
        target.update(
            {
                "is_credit_note": 1,
                "credit_note_against": source.name,
            }
        )

        for row in target.source_invoices:
            for field in distributed_fields:
                row.set(field, flt(-1 * flt(row.get(field), tax_precision), tax_precision))

    return _map_isd_invoice(
        source_name,
        target_doc,
        {
            "company": "company",
            "company_address": "company_address",
            "party_address": "party_address",
            "is_against_party": "is_against_party",
            "credit_flow": "credit_flow",
            "party_type": "party_type",
            "party": "party",
            "party_account": "party_account",
            "default_distribution_ratio": "default_distribution_ratio",
        },
        post_process,
        True,
    )
