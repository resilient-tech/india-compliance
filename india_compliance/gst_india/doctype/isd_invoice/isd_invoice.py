# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from collections import Counter, defaultdict
from functools import reduce
from operator import add

import frappe
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
    get_accounting_dimensions,
)
from erpnext.accounts.general_ledger import make_gl_entries, make_reverse_gl_entries
from erpnext.accounts.party import get_party_account
from erpnext.accounts.utils import get_fiscal_year
from erpnext.controllers.accounts_controller import AccountsController
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.model.meta import get_field_precision
from frappe.query_builder.functions import Coalesce, Date, IfNull, Sum
from frappe.utils import cint, flt, get_filtered_list_link, get_link_to_form, getdate, today

from india_compliance.gst_india.constants import (
    GST_TAX_TYPES,
)
from india_compliance.gst_india.doctype.pan.pan import get_pan_status
from india_compliance.gst_india.doctype.turnover_record.turnover_record import upsert_turnover_record
from india_compliance.gst_india.overrides.transaction import validate_gstin_status
from india_compliance.gst_india.utils import (
    get_gst_accounts_by_type,
    get_place_of_supply,
    is_valid_pan,
)
from india_compliance.gst_india.utils.isd import (
    CREDIT_FLOW,
    ISD_GST_CATEGORY,
    calculate_distribution,
    get_isd_source_item_query,
    get_pi_total_tax_map,
    sum_row_tax_by_type,
)


class ISDInvoice(Document):
    get_gl_dict = AccountsController.get_gl_dict
    get_value_in_transaction_currency = AccountsController.get_value_in_transaction_currency
    get_voucher_subtype = AccountsController.get_voucher_subtype
    company_currency = AccountsController.company_currency
    validate_account_currency = AccountsController.validate_account_currency

    def before_validate(self):
        self.set_taxes_and_totals()
        self.set_pos_from_gstin()
        self.clear_fields_when_is_against_party_not_set()

    def validate(self):
        self.validate_isd_party()
        self.validate_gstin_and_pos()
        if self.is_external_invoice:
            return
        self.validate_purchase_invoices()
        # TODO: add index in purchase invoice
        # TODO: gl entries should reduce/increase values in gl report
        self.validate_inter_company_transaction()
        self.validate_distribution_limits()

    def set_taxes_and_totals(self):
        self._tax_precision = self.precision("tax_amount", "taxes")
        self._source_item_precision = self.precision("distributed_igst", "source_invoices")

        self.set_distributed_taxes()
        self.set_distribution_totals()

    def set_distributed_taxes(self):
        if not self.source_invoices:
            self.taxes = []
            return

        accounts = get_gst_accounts_by_type(self.company, "Input", throw=False) or {}
        existing_taxes = {tax.gst_tax_type: tax for tax in self.taxes}

        for gst_tax_type in GST_TAX_TYPES:
            account_head = accounts.get(f"{gst_tax_type}_account")
            if not account_head:
                continue

            tax_amount = flt(
                sum(
                    flt(row.get(f"distributed_{gst_tax_type}"), self._source_item_precision)
                    for row in self.source_invoices
                ),
                self._tax_precision,
            )

            tax = existing_taxes.get(gst_tax_type)
            if tax:
                tax.account_head = account_head
                tax.tax_amount = tax_amount
            elif tax_amount:
                self.append(
                    "taxes",
                    {
                        "account_head": account_head,
                        "gst_tax_type": gst_tax_type,
                        "tax_amount": tax_amount,
                    },
                )
        # remove rows with zero tax amount, keeping existing sequence
        self.taxes = [tax for tax in self.taxes if tax.tax_amount]

    def set_distribution_totals(self):
        totals = {"eligible": 0, "ineligible": 0}

        for row in self.source_invoices:
            key = "ineligible" if row.is_ineligible_for_itc else "eligible"
            totals[key] += sum_row_tax_by_type(row, "distributed")

        total_precision = self.precision("total_eligible")
        self.total_eligible = flt(totals["eligible"], total_precision)
        self.total_ineligible = flt(totals["ineligible"], total_precision)

    def set_pos_from_gstin(self):
        gst_state_number, gst_state = frappe.get_value(
            "Address", self.company_address, ["gst_state_number", "gst_state"]
        )
        self.company_pos = f"{gst_state_number}-{gst_state}"

    def clear_fields_when_is_against_party_not_set(self):
        if self.is_against_party:
            return

        for field in ("party_type", "party", "credit_flow", "party_account"):
            if self.get(field):
                self.set(field, None)

    def validate_isd_party(self):
        addresses = [self.company_address, self.party_address]
        gst_categories = frappe._dict(
            frappe.db.get_all(
                "Address",
                filters={"name": ("in", addresses)},
                fields=["name", "gst_category"],
                as_list=True,
            )
        )

        if not self.is_against_party:
            if not gst_categories[self.company_address] == ISD_GST_CATEGORY:
                frappe.throw(
                    _("At least one party must be registered as an Input Service Distributor (ISD).")
                )
            return

        label, address = (
            (_("Company"), self.company_address)
            if self.credit_flow == CREDIT_FLOW.DISTRIBUTION
            else (_("Party"), self.party_address)
        )

        if gst_categories.get(address) != ISD_GST_CATEGORY:
            frappe.throw(
                _("{0} address {1} is not registered as an Input Service Distributor (ISD).").format(
                    label, get_link_to_form("Address", address)
                )
            )

    def validate_gstin_and_pos(self):
        for gstin in (self.company_gstin, self.party_gstin):
            if gstin:
                validate_gstin_status(gstin, self)

        if not self.party_gstin or not self.company_gstin:
            return

        company_pan = self.company_gstin[2:12]
        party_pan = self.party_gstin[2:12]

        if company_pan != party_pan:
            frappe.throw(
                _("PAN of Company GSTIN {0} and Party GSTIN {1} must be the same.").format(
                    frappe.bold(self.company_gstin), frappe.bold(self.party_gstin)
                )
            )

    def validate_purchase_invoices(self):
        self._pi_names = list({row.purchase_invoice for row in self.source_invoices})
        self._pi_rows = frappe.db.get_all(
            "Purchase Invoice",
            filters={"name": ("in", self._pi_names)},
            fields=["name", "docstatus", "is_isd_applicable", "posting_date", "company"],
        )
        self._validate_source_invoices_exsist()
        self._validate_duplication()
        self._validate_purchase_invoice_is_distributable()
        self._validate_source_invoice_dates()
        self._validate_source_invoices_with_inter_company_reference()
        self._validate_pi_with_company()

    def _validate_source_invoices_exsist(self):
        if not self.source_invoices:
            return frappe.throw(_("At least one source invoice must be added."))

    def _validate_duplication(self):
        keys = [(row.purchase_invoice, cint(row.is_ineligible_for_itc)) for row in self.source_invoices]
        if len(keys) == len(set(keys)):
            return

        seen = set()
        duplicates = {k for k in keys if k in seen or seen.add(k)}

        frappe.throw(
            _("Duplicate entries in Source Invoices: {0}").format(
                ", ".join(
                    f"{pi} ({_('Ineligible') if ineligible else _('Eligible')})"
                    for pi, ineligible in duplicates
                )
            )
        )

    def _validate_purchase_invoice_is_distributable(self):
        invalid_purchase_invoices = [
            row.name for row in self._pi_rows if row.docstatus != 1 or not row.is_isd_applicable
        ]
        if invalid_purchase_invoices:
            frappe.throw(_("Following purchase invoices are invalid - {0}").format(invalid_purchase_invoices))

    def _validate_source_invoice_dates(self):
        rows = [row.name for row in self._pi_rows if getdate(row.posting_date) > getdate(self.posting_date)]
        if rows:
            frappe.throw(
                _(
                    "The following purchase invoices are dated after this ISD invoice"
                    " and cannot be distributed (GSTR-6 Rule 39): {0}"
                ).format(get_filtered_list_link("Purchase Invoice", rows))
            )

    def _validate_pi_with_company(self):
        if self.credit_flow == CREDIT_FLOW.RECEIPT:
            return

        invalid_invoices = [row.name for row in self._pi_rows if row.company != self.company]
        if invalid_invoices:
            frappe.throw(
                _("Following Purchase Invoices do not belong to company {0}: {1}").format(
                    self.company, ", ".join(invalid_invoices)
                )
            )

    def _validate_source_invoices_with_inter_company_reference(self):
        if not (
            self.is_against_party
            and self.credit_flow == CREDIT_FLOW.RECEIPT
            and self.inter_company_invoice_reference
        ):
            return

        reference_invoices = frappe.get_all(
            "ISD Invoice Source Item",
            pluck="purchase_invoice",
            filters={"parent": self.inter_company_invoice_reference},
        )

        missing_invoices = set(reference_invoices) - set(self._pi_names)
        if missing_invoices:
            frappe.throw(
                _("Following Purchase Invoices from the inter company ISD Invoice are missing: {0}").format(
                    ", ".join(missing_invoices)
                )
            )

    def validate_inter_company_transaction(self):
        if not self.is_against_party or not self.party:
            return

        internal = "is_internal_supplier" if self.party_type == "Supplier" else "is_internal_customer"

        if frappe.db.get_value(self.party_type, {"name": self.party, internal: 1}, "name") != self.party:
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
        if self.is_against_party and self.credit_flow == CREDIT_FLOW.RECEIPT:
            return

        already_distributed = self.get_already_distributed_amounts()
        self._already_distributed_map = already_distributed  # used in on submit hooks
        invalid_distributions = []
        for row in self.source_invoices:
            key = (row.purchase_invoice, cint(row.is_ineligible_for_itc))
            distributed = sum_row_tax_by_type(row, "distributed")
            prior = already_distributed.get(key, 0)

            if self.is_credit_note:
                if prior + distributed < 0:
                    invalid_distributions.append((*key, prior, abs(distributed)))
            else:
                available = sum_row_tax_by_type(row, "total") - prior
                if distributed > available:
                    invalid_distributions.append((*key, available, distributed))

        if invalid_distributions:
            self.throw_invalid_distributions(invalid_distributions)

    def get_already_distributed_amounts(self):
        """{(purchase_invoice, is_ineligible_for_itc): net distributed} from other submitted ISD invoices."""
        isd_source_item = frappe.qb.DocType("ISD Invoice Source Item")
        isd_invoice = frappe.qb.DocType("ISD Invoice")
        rows = (
            get_isd_source_item_query(
                purchase_invoices=list({row.purchase_invoice for row in self.source_invoices})
            )
            .select(isd_source_item.is_ineligible_for_itc)
            .groupby(isd_source_item.purchase_invoice, isd_source_item.is_ineligible_for_itc)
            .where(isd_invoice.name != (self.name or ""))
            .run(as_dict=True)
        )

        return {
            (row.purchase_invoice, cint(row.is_ineligible_for_itc)): flt(
                row.total_distributed, self._source_item_precision
            )
            for row in rows
        }

    def throw_invalid_distributions(self, invalid_distributions):
        if self.is_credit_note:
            title, left_label, right_label = (
                _("Invalid Credit Note Reversal"),
                _("Originally Distributed"),
                _("Reversing"),
            )
        else:
            title, left_label, right_label = _("Invalid Tax Distribution"), _("Available"), _("Distributed")

        table = [[_("Purchase Invoice"), _("Type"), left_label, right_label]] + [
            [
                purchase_invoice,
                _("Ineligible") if is_ineligible else _("Eligible"),
                f"{left:.2f}",
                f"{right:.2f}",
            ]
            for purchase_invoice, is_ineligible, left, right in invalid_distributions
        ]
        frappe.msgprint(table, title=title, as_table=True, raise_exception=frappe.ValidationError)

    def on_submit(self):
        self._sync_purchase_invoice_distribution()
        make_gl_entries(self.get_gl_entries(), merge_entries=False)

    def on_cancel(self):
        self._sync_purchase_invoice_distribution()
        self.ignore_linked_doctypes = ("GL Entry",)
        make_reverse_gl_entries(voucher_type=self.doctype, voucher_no=self.name)

    def get_gl_entries(self):
        gl_entries = []
        party_id = self.party_gstin or self.party
        company_id = self.company_gstin or self.company_pos

        def add_gl_entry(account, debit=0, credit=0, remarks=None, company_gstin=None, **attributes):
            gl_dict = {
                "account": account,
                "debit": debit,
                "credit": credit,
                "remarks": remarks,
                **attributes,
            }
            # company_gstin only when available
            if company_gstin:
                gl_dict["company_gstin"] = company_gstin
            gl_entries.append(self.get_gl_dict(gl_dict))

        if not self.is_against_party:
            # credit the tax accounts (reduce), debit same accounts (restore at receiving end)
            for tax in self.taxes:
                if not tax.tax_amount:
                    continue
                add_gl_entry(
                    account=tax.account_head,
                    credit=tax.tax_amount,
                    remarks=f"ITC Distribution by {company_id}",
                    cost_center=self.cost_center,
                    company_gstin=self.company_gstin,
                )
                add_gl_entry(
                    account=tax.account_head,
                    debit=tax.tax_amount,
                    remarks=f"ITC Received by {party_id}",
                    cost_center=self.cost_center,
                    company_gstin=self.party_gstin,
                )

            return gl_entries

        is_distribution = self.credit_flow == CREDIT_FLOW.DISTRIBUTION
        total_tax = flt(sum(flt(tax.tax_amount) for tax in self.taxes))

        for tax in self.taxes:
            amount = flt(tax.tax_amount)
            if not amount:
                continue
            add_gl_entry(
                account=tax.account_head,
                debit=0 if is_distribution else amount,
                credit=amount if is_distribution else 0,
                # Distribution: tax leaves ISD; Receipt: tax enters company
                remarks=f"ITC Distribution to {party_id}"
                if is_distribution
                else f"ITC Received from {company_id}",
                company_gstin=self.company_gstin if is_distribution else self.party_gstin,
            )

        if self.party_account and total_tax:
            add_gl_entry(
                account=self.party_account,
                party_type=self.party_type,
                party=self.party,
                debit=total_tax if is_distribution else 0,
                credit=0 if is_distribution else total_tax,
                # Distribution: Customer account (receivable); Receipt: Supplier account (payable)
                remarks=f"ITC Receivable from {party_id}"
                if is_distribution
                else f"ITC Payable to {company_id}",
                company_gstin=self.party_gstin if is_distribution else self.company_gstin,
            )

        return gl_entries

    def _sync_purchase_invoice_distribution(self):

        # on_cancel does not run validate(), so set_taxes_and_totals() never sets this
        self._source_item_precision = self.precision("distributed_igst", "source_invoices")

        total_tax_map = defaultdict(float)
        dist_map = defaultdict(float)

        for row in self.source_invoices:
            if row.purchase_invoice:
                total_tax_map[row.purchase_invoice] += sum_row_tax_by_type(row, "total")
                if self.docstatus == 1:
                    dist_map[row.purchase_invoice] += sum_row_tax_by_type(row, "distributed")

        # reuse the map cached during validate(); on_cancel skips validate(), so rebuild it there.
        if not hasattr(self, "_already_distributed_map"):
            self._already_distributed_map = self.get_already_distributed_amounts()

        # merge its (pi, eligible) and (pi, ineligible) entries into a single per-PI total
        for (name, _is_ineligible), amount in self._already_distributed_map.items():
            dist_map[name] += amount

        doc_updates = {}
        for name in self._pi_names:
            total_tax = flt(total_tax_map.get(name, 0), self._source_item_precision)
            total_distributed = flt(dist_map.get(name, 0), self._source_item_precision)
            percent = flt(total_distributed / total_tax * 100 if total_tax else 0)
            doc_updates[name] = {"isd_credit_distributed_percent": percent}

        frappe.db.bulk_update("Purchase Invoice", doc_updates, update_modified=False)

    @frappe.whitelist()
    def get_purchase_invoices(self, purchase_invoices: list, distribution_ratio: float = 0.0):
        if not purchase_invoices:
            frappe.msgprint(_("No Purchase Invoices selected"))
            return []

        frappe.has_permission("Purchase Invoice", "read", throw=True)
        frappe.has_permission("ISD Invoice", "write", throw=True)

        # exsisting non empty items
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


def _calculate_distribution(doc):
    calculate_distribution(doc)
    doc.set_taxes_and_totals()


@frappe.whitelist()
def get_source_invoices_from_purchase_invoices(purchase_invoices: list | str):
    frappe.has_permission("Purchase Invoice", "read", throw=True)
    frappe.has_permission("ISD Invoice", "create", throw=True)

    if isinstance(purchase_invoices, str):
        purchase_invoices = frappe.parse_json(purchase_invoices)

    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")
    return (
        frappe.qb.from_(pi_item)
        .where(pi_item.docstatus == 1)
        .where(pi.parent.isin(purchase_invoices))
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
    parties = frappe.get_list(doc.party_type, filters={internal_field: 1}, pluck="name", limit=1)
    return parties[0] if parties else None


PARTY_RESOLVERS = {
    "credit_flow": _resolve_credit_flow,
    "party_type": _resolve_party_type,
    "party": _resolve_party,
}


def _resolve_party_account(doc):
    if not (doc.is_against_party and doc.company and doc.party_type):
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
    PARTY_CHAIN = ("is_against_party", "credit_flow", "party_type", "party")

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
    return get_gst_accounts_by_type(company, "Input", throw=False)


@frappe.whitelist()
def search_purchase_invoice(txt: str, company: str, billing_address: str | None = None):
    filters = [
        ["docstatus", "=", 1],
        ["company", "=", company],
        ["name", "like", f"%{txt}%"],
    ]
    if billing_address:
        filters.append(["billing_address", "=", billing_address])

    return frappe.get_list("Purchase Invoice", filters=filters, pluck="name", limit=20)


def _map_isd_invoice(source_name, target_doc, field_map, post_process):
    item_fields = [
        "purchase_invoice",
        "is_ineligible_for_itc",
        "distribution_ratio",
        "distribution_amount",
        *[f"total_{tax_type}" for tax_type in GST_TAX_TYPES],
        *[f"distributed_{tax_type}" for tax_type in GST_TAX_TYPES],
    ]

    meta = frappe.get_meta("ISD Invoice")
    accounting_dimension_field_map = {}
    for fieldname in get_accounting_dimensions(as_list=True):
        if meta.has_field(fieldname):
            accounting_dimension_field_map[fieldname] = fieldname

    return get_mapped_doc(
        "ISD Invoice",
        source_name,
        {
            "ISD Invoice": {
                "doctype": "ISD Invoice",
                "validation": {"docstatus": ["=", 1]},
                "field_map": {**accounting_dimension_field_map, **field_map},
            },
            "ISD Invoice Source Item": {
                "doctype": "ISD Invoice Source Item",
                "field_map": item_fields,
            },
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
                _("invoice created with missing fields values"),
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
    )


@frappe.whitelist()
def get_distribution_addresses(party_type: str, party: str, posting_date: str, address: str | None = None):
    addr = frappe.qb.DocType("Address")
    dynamic_link = frappe.qb.DocType("Dynamic Link")
    turnover_record = frappe.qb.DocType("Turnover Record")

    query = (
        frappe.qb.from_(addr)
        .join(dynamic_link)
        .on(dynamic_link.parent == addr.name)
        .left_join(turnover_record)
        .on(
            (IfNull(turnover_record.gstin, "") == IfNull(addr.gstin, ""))
            & (IfNull(turnover_record.gst_state, "") == IfNull(addr.gst_state, ""))
        )
        .select(
            addr.name,
            addr.gstin,
            addr.gst_state,
            addr.gst_category,
            Coalesce(turnover_record.amount, 0).as_("turnover_amount"),
        )
        .where(
            (dynamic_link.link_doctype == party_type)
            & (dynamic_link.link_name == party)
            & (addr.gst_category != ISD_GST_CATEGORY)
        )
        .where(
            (turnover_record.from_date.isnull())
            | (Date(posting_date).between(turnover_record.from_date, turnover_record.to_date))
        )
    )

    if address:
        query = query.where(addr.name == address)

    return query.run(as_dict=True)


def make_isd_invoice(
    source_purchase_invoices: dict,
    target_doc: str | None = None,
    party_address: str | None = None,
    party_type: str | None = None,
    party: str | None = None,
    individual_turnover: float | None = None,
    total_turnover: float | None = None,
):
    """Create one ISD Invoice distributing a portion of each source PI's tax to a single party/address.

    source_purchase_invoices maps each purchase invoice to (amount_to_distribute, total_tax_available).
    Per row the distribution ratio is the address' turnover share scaled by how much of that PI's tax
    is being distributed: (individual_turnover / total_turnover) * (amount_to_distribute / total_tax).
    """
    is_against_party = 1 if party_type in ["Customer", "Supplier"] and party else 0
    source_names = list(source_purchase_invoices)
    seed_name = source_names[0]

    turnover_ratio = individual_turnover / total_turnover if individual_turnover and total_turnover else 0.0

    def set_missing_values(source, target):
        target.party_address = party_address

        if party_type and party:
            target.is_against_party = is_against_party
            target.party_type = party_type
            target.party = party

        result = get_source_invoices_from_purchase_invoices(source_names)
        if not result:
            frappe.throw(
                _("Purchase Invoice(s) {0} have no taxable amount to distribute.").format(
                    frappe.bold(", ".join(source_names))
                )
            )

        for row in result:
            amount_to_distribute, total_tax = source_purchase_invoices[row.purchase_invoice]
            scale = flt(amount_to_distribute) / total_tax if total_tax else 0.0
            target.append(
                "source_invoices",
                {**row, "distribution_ratio": turnover_ratio * scale * 100},
            )

        _calculate_distribution(target)

    doc = get_mapped_doc(
        "Purchase Invoice",
        seed_name,
        {
            "Purchase Invoice": {
                "doctype": "ISD Invoice",
                "field_map": {
                    "company": "company",
                    "billing_address": "company_address",
                },
                "field_no_map": ["naming_series", "party_address"],
                "validation": {
                    "docstatus": ["=", 1],
                    "is_isd_applicable": ["=", 1],
                },
            },
        },
        target_doc,
        postprocess=set_missing_values,
    )

    doc.flags.ignore_validate = True
    doc.insert(ignore_permissions=True)

    doc.flags.ignore_validate = False
    try:
        doc.save()
    except frappe.ValidationError:
        frappe.clear_messages()
        return doc, True

    return doc, False


@frappe.whitelist()
def get_purchase_invoices_distribution_summary(purchase_invoices: list | str):
    """Per purchase invoice: posting date, supplier, total tax and tax still available to distribute."""
    frappe.has_permission("Purchase Invoice", "read", throw=True)
    if isinstance(purchase_invoices, str):
        purchase_invoices = frappe.parse_json(purchase_invoices)

    if not purchase_invoices:
        return []

    pi_details = {
        row.name: row
        for row in frappe.get_all(
            "Purchase Invoice",
            filters={"name": ("in", purchase_invoices)},
            fields=["name", "posting_date", "supplier"],
        )
    }

    total_tax_map = dict(get_pi_total_tax_map(purchase_invoices).run())

    isd_source_item = frappe.qb.DocType("ISD Invoice Source Item")
    distributed_map = dict(
        get_isd_source_item_query(purchase_invoices=purchase_invoices)
        .groupby(isd_source_item.purchase_invoice)
        .run()
    )

    result = []
    for name in purchase_invoices:
        details = pi_details.get(name) or frappe._dict()
        total_tax = total_tax_map.get(name, 0)
        distributed = distributed_map.get(name, 0)
        result.append(
            {
                "purchase_invoice": name,
                "posting_date": details.get("posting_date"),
                "supplier": details.get("supplier"),
                "total_tax": total_tax,
                "available_to_distribute": total_tax - distributed,
            }
        )

    return result


@frappe.whitelist()
def bulk_create_isd_invoices(distribution_table: list | str, purchase_invoices: dict | str):
    """Create ISD invoices distributing `purchase_invoices` ({pi: amount_to_distribute}) across addresses."""
    frappe.has_permission("ISD Invoice", "write", throw=True)
    frappe.has_permission("Purchase Invoice", "read", throw=True)

    if isinstance(distribution_table, str):
        distribution_table = frappe.parse_json(distribution_table)
    if isinstance(purchase_invoices, str):
        purchase_invoices = frappe.parse_json(purchase_invoices)

    if not purchase_invoices:
        frappe.throw(_("No Purchase Invoices provided."))

    # drop addresses with no turnover - they would distribute nothing
    distribution_table = [row for row in distribution_table if flt(row["turnover_amount"] or 0)]

    total_turnover = sum(flt(row.get("turnover_amount") or 0) for row in distribution_table)
    total_tax_map = dict(get_pi_total_tax_map(purchase_invoices).run())

    # {pi: (amount_to_distribute, total_tax_available)}
    tax_precision = get_field_precision(
        frappe.get_meta("ISD Invoice Source Item").get_field("distributed_igst")
    )
    source_purchase_invoices = {
        name: (flt(amount), flt(total_tax_map.get(name, 0), tax_precision))
        for name, amount in purchase_invoices.items()
    }

    pi_records = frappe.get_list(
        "Purchase Invoice",
        filters={"name": ["in", list(purchase_invoices)]},
        fields=["name", "billing_address"],
    )
    by_billing: dict[str, dict] = defaultdict(dict)
    for pi in pi_records:
        by_billing[pi.billing_address][pi.name] = source_purchase_invoices[pi.name]

    for row in distribution_table:
        upsert_turnover_record(row["gstin"], row["gst_state"], row["turnover_amount"])

    invoice_tasks = [(pi_group, row) for pi_group in by_billing.values() for row in distribution_table]

    invoices, invalid_invoices = [], []
    for pi_group, row in invoice_tasks:
        isd_doc, is_invalid = make_isd_invoice(
            source_purchase_invoices=pi_group,
            target_doc=None,
            party_address=row["party_address"],
            party_type=row["party_type"],
            party=row["party"],
            individual_turnover=flt(row["turnover_amount"]),
            total_turnover=total_turnover,
        )
        invoices.append(isd_doc.name)
        if is_invalid:
            invalid_invoices.append(isd_doc.name)

    target_total = flt(sum(amount for amount, _ in source_purchase_invoices.values()), tax_precision)
    _absorb_remainder_post_save(invoices, target_total)

    return invoices, invalid_invoices


def _absorb_remainder_post_save(invoice_names, target_total):
    """Push the rounding remainder (target_total - actually distributed) into the last ISD invoice."""
    if not invoice_names:
        return

    tax_precision = get_field_precision(
        frappe.get_meta("ISD Invoice Source Item").get_field("distributed_igst")
    )

    isd_source_item = frappe.qb.DocType("ISD Invoice Source Item")
    distributed_row = (
        frappe.qb.from_(isd_source_item)
        .where(isd_source_item.parent.isin(invoice_names))
        .select(
            Sum(reduce(add, (isd_source_item[f"distributed_{t}"] for t in GST_TAX_TYPES))).as_(
                "total_distributed"
            )
        )
        .run(as_dict=True)
    )
    total_distributed = flt((distributed_row[0].total_distributed if distributed_row else 0), tax_precision)

    difference = flt(flt(target_total, tax_precision) - total_distributed, tax_precision)

    if not difference:
        return

    _adjust_last_isd_invoice(difference, invoice_names[-1])


def _adjust_last_isd_invoice(difference, last_isd_invoice):
    distributed_fields = [f"distributed_{t}" for t in GST_TAX_TYPES]
    items = frappe.get_all(
        "ISD Invoice Source Item",
        filters={"parent": last_isd_invoice},
        fields=["name", *distributed_fields],
        limit=1,
    )
    if not items:
        return

    item = items[0]
    field = next((f for f in distributed_fields if flt(item.get(f))), None)
    if not field:
        field = distributed_fields[0]

    frappe.db.set_value(
        "ISD Invoice Source Item",
        item.name,
        field,
        flt(item.get(field)) + difference,
        update_modified=False,
    )
