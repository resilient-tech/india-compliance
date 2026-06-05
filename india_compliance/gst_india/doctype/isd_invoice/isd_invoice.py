# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from collections import defaultdict
from functools import reduce
from operator import add

import frappe
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
    get_accounting_dimensions,
)
from erpnext.accounts.party import get_party_account
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.model.meta import get_field_precision
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import cint, flt, get_filtered_list_link, get_link_to_form, today
from pypika.terms import Case

from india_compliance.gst_india.constants import (
    CREDIT_FLOW,
    GST_TAX_TYPES,
    ISD_GST_CATEGORY,
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
    calculate_distribution,
    get_isd_source_item_query,
    sum_row_tax_by_type,
)


class ISDInvoice(Document):
    def before_validate(self):
        self.set_taxes_and_totals()
        self.set_pos_from_gstin()
        self.clear_fields_when_is_against_party_not_set()

    def validate(self):
        self.validate_isd_party()
        self.validate_gstin_and_pan()
        self.validate_source_invoice_dates()
        self.validate_duplication()
        self.validate_inter_company_transaction()
        self.validate_distribution_limits()
        # TODO: validate that purchase invoice is of the given company only. if not mentioned then its mandatory to add acknowlege that

    def set_taxes_and_totals(self):
        self.set_distributed_taxes()
        self.set_distribution_totals()

    def set_distributed_taxes(self):
        self.taxes = []
        if not self.source_invoices:
            return

        tax_precision = get_field_precision(frappe.get_meta("ISD Invoice Tax Item").get_field("tax_amount"))
        accounts = get_gst_accounts_by_type(self.company, "Input", throw=False) or {}
        for gst_tax_type in GST_TAX_TYPES:
            account_head = accounts.get(f"{gst_tax_type}_account")
            tax_amount = flt(
                sum(flt(row.get(f"distributed_{gst_tax_type}")) for row in self.source_invoices),
                tax_precision,
            )
            if not account_head or not tax_amount:
                continue

            self.append(
                "taxes",
                {
                    "account_head": account_head,
                    "gst_tax_type": gst_tax_type,
                    "tax_amount": tax_amount,
                },
            )

    def set_distribution_totals(self):
        totals = {"eligible": 0, "ineligible": 0}

        for row in self.source_invoices:
            key = "ineligible" if row.is_ineligible_for_itc else "eligible"
            totals[key] += sum_row_tax_by_type(row, "distributed")

        total_precision = get_field_precision(frappe.get_meta("ISD Invoice").get_field("total_eligible"))
        self.total_eligible = flt(totals["eligible"], total_precision)
        self.total_ineligible = flt(totals["ineligible"], total_precision)

    def set_pos_from_gstin(self):
        self.company_pos = (
            get_place_of_supply(frappe._dict(company_gstin=self.company_gstin), "ISD Invoice")
            if self.company_gstin
            else None
        )
        self.party_pos = (
            get_place_of_supply(frappe._dict(company_gstin=self.party_gstin), "ISD Invoice")
            if self.party_gstin
            else None
        )

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
            if not any(category == ISD_GST_CATEGORY for category in gst_categories.values()):
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

    def validate_gstin_and_pan(self):
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

        if not is_valid_pan(company_pan):
            frappe.throw(_("PAN {0} derived from GSTIN is not a valid PAN.").format(frappe.bold(company_pan)))

        # API disabled upstream -> falls back to local PAN doctype; only throw on a known-invalid PAN
        if get_pan_status(company_pan)[0] == "Invalid":
            frappe.throw(_("PAN {0} is invalid as per Income Tax records.").format(frappe.bold(company_pan)))

    def validate_source_invoice_dates(self):
        if not self.source_invoices:
            return

        pi_names = list({row.purchase_invoice for row in self.source_invoices})
        rows = frappe.db.get_all(
            "Purchase Invoice",
            filters={"name": ("in", pi_names), "posting_date": (">", self.posting_date)},
            pluck="name",
        )
        if rows:
            frappe.throw(
                _(
                    "The following purchase invoices are dated after this ISD invoice"
                    " and cannot be distributed (GSTR-6 Rule 39): {0}"
                ).format(get_filtered_list_link("Purchase Invoice", rows))
            )

    def validate_duplication(self):
        keys = [(row.purchase_invoice, cint(row.is_ineligible_for_itc)) for row in self.source_invoices or []]
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
        if not self.source_invoices:
            return

        already_distributed = self.get_already_distributed_amounts()
        invalid_distributions = []
        for row in self.source_invoices:
            key = (row.purchase_invoice, row.is_ineligible_for_itc)
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
        """{(purchase_invoice, is_ineligible_for_itc): net distributed} from other submitted ISD invoices.

        Credit notes store distributed amounts as negative, so the Sum nets prior reversals.
        """
        isd_source_item = frappe.qb.DocType("ISD Invoice Source Item")
        isd_invoice = frappe.qb.DocType("ISD Invoice")
        rows = (
            get_isd_source_item_query(
                purchase_invoices=list({row.purchase_invoice for row in self.source_invoices})
            )
            .select(isd_source_item.is_ineligible_for_itc)
            .groupby(isd_source_item.is_ineligible_for_itc)
            .where(isd_invoice.name != (self.name or ""))
            .run(as_dict=True)
        )

        return {(row.purchase_invoice, row.is_ineligible_for_itc): flt(row.total_distributed) for row in rows}

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
        # TODO: add gl entry

    def on_cancel(self):
        self._sync_purchase_invoice_distribution()

    def _sync_purchase_invoice_distribution(self):
        purchase_invoices = list(
            {row.purchase_invoice for row in self.source_invoices if row.purchase_invoice}
        )
        if not purchase_invoices:
            return

        pi = frappe.qb.DocType("Purchase Invoice")
        pi_item = frappe.qb.DocType("Purchase Invoice Item")
        tax_rows = (
            frappe.qb.from_(pi_item)
            .join(pi)
            .on(pi_item.parent == pi.name)
            .where(pi.docstatus == 1)
            .where(pi.name.isin(purchase_invoices))
            .select(
                pi_item.parent.as_("purchase_invoice"),
                Sum(reduce(add, (pi_item[f"{t}_amount"] for t in GST_TAX_TYPES))).as_("total_tax"),
            )
            .groupby(pi_item.parent)
            .run(as_dict=True)
        )
        total_tax_map = {r.purchase_invoice: flt(r.total_tax) for r in tax_rows}

        isd_invoice = frappe.qb.DocType("ISD Invoice")
        dist_rows = (
            get_isd_source_item_query(purchase_invoices=purchase_invoices)
            .where(isd_invoice.posting_date >= self.posting_date)
            .run(as_dict=True)
        )
        dist_map = {r.purchase_invoice: flt(r.total_distributed) for r in dist_rows}

        if not total_tax_map:
            return

        purchase_invoice = frappe.qb.DocType("Purchase Invoice")
        case = Case()
        for name in purchase_invoices:
            total_tax = total_tax_map.get(name, 0)
            total_distributed = dist_map.get(name, 0)
            percent = total_distributed / total_tax * 100 if total_tax else 0
            case = case.when(purchase_invoice.name == name, percent)

        (
            frappe.qb.update(purchase_invoice)
            .set(
                purchase_invoice.isd_credit_distributed_percent,
                case.else_(purchase_invoice.isd_credit_distributed_percent),
            )
            .where(purchase_invoice.name.isin(purchase_invoices))
            .run()
        )

    @frappe.whitelist()
    def get_purchase_invoices(self, purchase_invoices: list, distribution_ratio: float = 0.0):
        if not purchase_invoices:
            frappe.msgprint(_("No Purchase Invoices selected"))
            return []

        frappe.has_permission("Purchase Invoice", "read", throw=True)
        frappe.has_permission("ISD Invoice", "write", throw=True)

        existing_items = [
            (item.purchase_invoice, item.is_ineligible_for_itc) for item in self.source_invoices
        ]
        items_to_add = get_source_invoices_from_purchase_invoices(purchase_invoices)

        for item in items_to_add:
            if (item.purchase_invoice, item.is_ineligible_for_itc) not in existing_items:
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
        .join(pi)
        .on(pi_item.parent == pi.name)
        .where(pi.docstatus == 1)
        .where(pi.name.isin(purchase_invoices))
        .select(
            pi_item.parent.as_("purchase_invoice"),
            pi_item.is_ineligible_for_itc,
            *[Sum(getattr(pi_item, f"{t}_amount")).as_(f"total_{t}") for t in GST_TAX_TYPES],
        )
        .groupby(pi_item.parent, pi_item.is_ineligible_for_itc)
        .having(Sum(reduce(add, (pi_item[f"{t}_amount"] for t in GST_TAX_TYPES))) > 0)
        .run(as_dict=True)
    )


@frappe.whitelist()
def get_purchase_invoices_distribution_summary(purchase_invoices: list | str):
    """Return total tax and already-distributed amounts per purchase invoice."""
    frappe.has_permission("Purchase Invoice", "read", throw=True)
    if isinstance(purchase_invoices, str):
        purchase_invoices = frappe.parse_json(purchase_invoices)

    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")
    rows = (
        frappe.qb.from_(pi_item)
        .join(pi)
        .on(pi_item.parent == pi.name)
        .where(pi.docstatus == 1)
        .where(pi.name.isin(purchase_invoices))
        .select(
            pi_item.parent.as_("purchase_invoice"),
            Sum(reduce(add, (pi_item[f"{t}_amount"] for t in GST_TAX_TYPES))).as_("total_tax"),
            pi.isd_credit_distributed_percent,
        )
        .groupby(pi_item.parent)
        .run(as_dict=True)
    )
    row_map = {r.purchase_invoice: r for r in rows}

    return [
        {
            "purchase_invoice": name,
            "total_tax": flt(row.total_tax) if (row := row_map.get(name)) else 0,
            "total_distributed": flt(row.total_tax) * flt(row.isd_credit_distributed_percent) / 100
            if (row := row_map.get(name))
            else 0,
        }
        for name in purchase_invoices
    ]


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

    is_outward = doc.credit_flow == CREDIT_FLOW.DISTRIBUTION
    return (
        fetch_address("Company", doc.company, exclude_isd=not is_outward),
        fetch_address(doc.party_type, doc.party, exclude_isd=not is_outward),
    )


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

        # Counterpart roles flip, so each address is found via the other side's GSTIN:
        # the source party's GSTIN belongs to the counterpart company, and vice-versa.
        company_address = (
            frappe.db.get_value(
                "Address", {"gstin": source.party_gstin}, "name", order_by="is_primary_address desc"
            )
            if source.party_gstin
            else None
        )

        party_address = (
            frappe.db.get_value(
                "Address", {"gstin": source.company_gstin}, "name", order_by="is_primary_address desc"
            )
            if source.company_gstin
            else None
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
                _("some fields are empty"),
                alert=True,
            )

    return _map_isd_invoice(
        source_name,
        target_doc,
        {
            "naming_series": "naming_series",
            "is_credit_note": "is_credit_note",
            "posting_date": "posting_date",
            "distribution_ratio": "distribution_ratio",
        },
        post_process,
    )


@frappe.whitelist()
def make_credit_note(source_name: str, target_doc: str | None = None):
    frappe.has_permission("ISD Invoice", "write", throw=True)

    distributed_fields = [f"distributed_{tax_type}" for tax_type in GST_TAX_TYPES]

    def post_process(source, target):
        target.update(
            {
                "is_credit_note": 1,
                "credit_note_against": source.name,
            }
        )

        for row in target.source_invoices:
            for field in distributed_fields:
                row.set(field, -1 * flt(row.get(field)))

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
            "distribution_ratio": "distribution_ratio",
        },
        post_process,
    )


@frappe.whitelist()
def get_distribution_addresses(party_type: str, party: str, posting_date: str, address: str | None = None):
    fy = get_fiscal_year(posting_date, company=party, raise_on_missing=False) or get_fiscal_year(
        today(), company=party, raise_on_missing=False
    )
    from_date = fy[1] if fy else None
    to_date = fy[2] if fy else None

    addr = frappe.qb.DocType("Address")
    dynamic_link = frappe.qb.DocType("Dynamic Link")
    turnover_record = frappe.qb.DocType("Turnover Record")

    query = (
        frappe.qb.from_(addr)
        .join(dynamic_link)
        .on(dynamic_link.parent == addr.name)
        .left_join(turnover_record)
        .on(
            (turnover_record.gstin == addr.gstin)
            & (turnover_record.gst_state == addr.gst_state)
            & (turnover_record.from_date == from_date)
            & (turnover_record.to_date == to_date)
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
    )

    if address:
        query = query.where(addr.name == address)

    return query.run(as_dict=True)


def make_isd_invoice(
    source_names: list,
    target_doc: str | None = None,
    party_address: str | None = None,
    party_type: str | None = None,
    party: str | None = None,
    individual_turnover: float | None = None,
    total_turnover: float | None = None,
):
    """
    Insert a new ISD Invoice based on one or more Purchase Invoices sharing the same billing_address.
    Permission checked in get_mapped_doc, validation ignored while inserting.
    """

    is_against_party = 1 if party_type in ["Customer", "Supplier"] and party else 0
    seed_name = source_names[0]

    def set_missing_values(source, target):
        distribution_ratio = (
            individual_turnover / total_turnover * 100 if individual_turnover and total_turnover else 0.0
        )
        target.distribution_ratio = distribution_ratio
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
            target.append("source_invoices", {**row, "distribution_ratio": distribution_ratio})

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
def bulk_create_isd_invoices(distribution_heads: list | str, source_names: list | str):
    frappe.has_permission("ISD Invoice", "write", throw=True)
    frappe.has_permission("Purchase Invoice", "read", throw=True)

    if isinstance(distribution_heads, str):
        distribution_heads = frappe.parse_json(distribution_heads)

    if isinstance(source_names, str):
        source_names = frappe.parse_json(source_names)

    if not source_names:
        frappe.throw(_("No Purchase Invoices provided."))

    pi_records = frappe.get_list(
        "Purchase Invoice",
        filters={"name": ["in", source_names]},
        fields=["name", "billing_address", "posting_date", "company"],
    )
    by_billing: dict[str, list] = defaultdict(list)
    for pi in pi_records:
        by_billing[pi.billing_address].append(pi.name)

    total_turnover = sum(flt(row.get("turnover_amount") or 0) for row in distribution_heads)

    invoices = []
    invalid_invoices = []

    for group_pi_by_billing_address in by_billing.values():
        for row in distribution_heads[:-1]:
            turnover_amount = row.get("turnover_amount") or 0
            if not turnover_amount:
                continue

            upsert_turnover_record(row["gstin"], row["gst_state"], turnover_amount)
            # TODO: add checkbox in dialog to not create isd records if errors occurs
            isd_doc, is_invalid_insertion = make_isd_invoice(
                source_names=group_pi_by_billing_address,
                target_doc=None,
                party_address=row["party_address"],
                party_type=row["party_type"],
                party=row["party"],
                individual_turnover=turnover_amount,
                total_turnover=total_turnover,
            )

            invoices.append(isd_doc.name)

            if is_invalid_insertion:
                invalid_invoices.append(isd_doc.name)

    return invoices, invalid_invoices
