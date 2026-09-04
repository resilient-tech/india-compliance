# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""Shared helpers for the Input Service Distributor (ISD) feature.

Imports only frappe / constants so it stays a leaf module that the ISD controllers can depend on
(one-directional).
"""

from functools import reduce
from operator import add

import frappe
from frappe import _
from frappe.model.meta import get_field_precision
from frappe.query_builder.functions import Coalesce, IfNull, Sum
from frappe.utils import cint, flt, get_link_to_form, getdate

from india_compliance.gst_india.constants import (
    GST_TAX_TYPES,
    IMPORT_GST_CATEGORIES,
    ISD_GST_CATEGORY,
)
from india_compliance.gst_india.doctype.turnover_record.turnover_record import (
    get_relevant_period,
    get_turnover_amount,
    upsert_turnover_record,
)
from india_compliance.gst_india.utils import get_gst_accounts_by_type

ISD_DOCTYPES = ("ISD Distribution Invoice", "ISD Recipient Invoice")


def sum_row_tax_by_type(row, prefix):
    """Python float sum of the five GST tax fields on a document/dict row (e.g. distributed_*, total_*)."""
    return sum(flt(row.get(f"{prefix}_{tax_type}")) for tax_type in GST_TAX_TYPES)


def get_existing_credit_note(doc):
    return frappe.db.exists(
        doc.doctype,
        {
            "credit_note_against": doc.credit_note_against,
            "is_credit_note": 1,
            "name": ("!=", doc.name or ""),
            "docstatus": ("<", 2),
        },
    )


def validate_single_credit_note(doc):
    if existing := get_existing_credit_note(doc):
        frappe.throw(
            _("{0} already has a credit note in {1}.").format(
                get_link_to_form(doc.doctype, doc.credit_note_against),
                get_link_to_form(doc.doctype, existing),
            ),
            title=_("Credit Note Already Exists"),
        )


def throw_row_table(title, header, rows):
    """Raise a ValidationError rendering all offending rows as a table under one title."""
    if not rows:
        return
    table = [[str(cell) for cell in row] for row in ([header, *rows])]
    frappe.msgprint(table, title=title, as_table=True, raise_exception=frappe.ValidationError)


def throw_invalid_rows(message, rows):
    """Raise a ValidationError listing the offending rows under a descriptive title, e.g.
    'Following source items do not belong to Purchase Invoice PINV-0001' over 'Row #1: ITEM-A'."""
    if not rows:
        return

    frappe.msgprint(
        [_("Row #{0}: {1}").format(idx, frappe.bold(value)) for idx, value in rows],
        title=message,
        as_list=True,
        raise_exception=frappe.ValidationError,
    )


def is_inter_state_distribution(doc):
    # SEZ / overseas recipients are always inter-state (IGST), regardless of place of supply
    _, recipient_address = doc.get_distribution_and_recipient_address()
    party_gst_category = (
        frappe.get_cached_value("Address", recipient_address, "gst_category") if recipient_address else None
    )
    if party_gst_category in IMPORT_GST_CATEGORIES:
        return True

    return doc.company_pos != doc.party_pos


def get_distribution_ratio(doc):
    """
    Signed turnover ratio (credit notes reverse credit, so they carry a negative sign).
    """
    total_turnover = flt(doc.total_turnover)
    if not total_turnover:
        return 0

    sign = -1 if doc.is_credit_note else 1
    return sign * flt(doc.branch_turnover) / total_turnover


def distribute_expense_with_isd_credit():
    return cint(frappe.get_cached_value("GST Settings", "GST Settings", "distribute_expense_with_isd_credit"))


def get_row_itc(row, is_distribution, precision, ratio=None):
    """Row-wise ITC per GST head.

    distribution side -> drawn from the source heads: ``flt(total_<head> * ratio)``
    recipient side    -> the already-converted amounts: ``flt(distributed_<head>)``
    """
    if is_distribution:
        return {
            gst_tax_type: flt(abs(flt(row.get(f"total_{gst_tax_type}"))) * ratio, precision)
            for gst_tax_type in GST_TAX_TYPES
        }
    return {
        gst_tax_type: flt(row.get(f"distributed_{gst_tax_type}"), precision) for gst_tax_type in GST_TAX_TYPES
    }


def calculate_distribution(doc):
    ratio = get_distribution_ratio(doc)
    inter_state = is_inter_state_distribution(doc)
    distribute_expense = distribute_expense_with_isd_credit()

    meta = frappe.get_meta("ISD Source Item")
    precision = get_field_precision(meta.get_field("distributed_igst"))
    expense_precision = get_field_precision(meta.get_field("distributed_expense"))

    for row in doc.source_items or []:
        credit = get_row_itc(row, True, precision, ratio)

        if inter_state:
            # inter-state -> the recipient receives everything as IGST (Rule 39(1)(e), (g)).
            # Sum the already-rounded parts so distributed_igst == CGST + SGST + IGST booked in taxes.
            row.distributed_igst = flt(credit["igst"] + credit["cgst"] + credit["sgst"], precision)
            row.distributed_cgst = 0.0
            row.distributed_sgst = 0.0
        else:
            # intra-state -> each credit keeps its type (Rule 39(1)(e), (f))
            row.distributed_igst = credit["igst"]
            row.distributed_cgst = credit["cgst"]
            row.distributed_sgst = credit["sgst"]

        # cess is never fused, whatever the place of supply
        row.distributed_cess = credit["cess"]
        row.distributed_cess_non_advol = credit["cess_non_advol"]
        row.distributed_expense = (
            flt(abs(flt(row.total_expense)) * ratio, expense_precision) if distribute_expense else 0.0
        )


@frappe.whitelist()
def get_source_items_from_purchase_invoice(purchase_invoice: str):
    if not purchase_invoice:
        return []

    frappe.has_permission("Purchase Invoice", "read", doc=purchase_invoice, throw=True)

    # selected under the ISD Source Item fieldnames, so the rows drop straight into the child table
    source_items = frappe.get_all(
        "Purchase Invoice Item",
        filters={"parent": purchase_invoice},
        fields=[
            "name as purchase_invoice_item",
            "item_code",
            "item_name",
            "gst_hsn_code",
            "is_ineligible_for_itc",
            "cost_center",
            "project",
            "expense_account as expense_head",
            "base_net_amount as total_expense",
            "igst_amount as total_igst",
            "cgst_amount as total_cgst",
            "sgst_amount as total_sgst",
            "cess_amount as total_cess",
            "cess_non_advol_amount as total_cess_non_advol",
        ],
        order_by="idx",
    )

    return source_items


def get_purchase_doc(purchase_invoice: str):
    if not purchase_invoice:
        frappe.throw(_("Purchase Invoice is required."))

    doc = frappe.db.get_value(
        "Purchase Invoice",
        purchase_invoice,
        [
            "name",
            "company",
            "company_gstin",
            "posting_date",
            "billing_address",
            "docstatus",
            "is_isd_applicable",
            "is_return",
        ],
        as_dict=True,
    )

    pi_link = get_link_to_form("Purchase Invoice", purchase_invoice)
    if not doc or doc.docstatus != 1:
        frappe.throw(_("Purchase Invoice {0} is not submitted.").format(pi_link))

    if not doc.is_isd_applicable:
        frappe.throw(_("Purchase Invoice {0} is not ISD applicable.").format(pi_link))

    doc.source_items = get_source_items_from_purchase_invoice(purchase_invoice)

    return doc


def get_place_of_supply_for_address(address):
    """Place of Supply in the `<state number>-<state>` form both ISD doctypes store."""
    if not address:
        return None

    state_number, state = frappe.db.get_value("Address", address, ["gst_state_number", "gst_state"])
    return f"{state_number}-{state}" if state else None


@frappe.whitelist()
def get_isd_place_of_supply(address: str):
    frappe.has_permission("Address", "read", doc=address, throw=True)
    return get_place_of_supply_for_address(address)


@frappe.whitelist()
def get_input_gst_accounts(company: str):
    frappe.has_permission("Company", doc=company, throw=True)
    return get_gst_accounts_by_type(company, "Input")


# ---------------------------------------------------------------------------- autofill
# The party chain both ISD doctypes share
_PARTY_CHAIN = ("company", "is_against_party", "party_type", "party")


def _resolve_isd_party_type(doc, is_company_isd):
    if not doc.is_against_party:
        return None
    # by default distribution passes credit to an internal Customer; the recipient receives it from an internal Supplier
    return "Customer" if is_company_isd else "Supplier"


def _resolve_isd_party(doc):
    if not (doc.is_against_party and doc.party_type):
        return None

    internal_field = "is_internal_customer" if doc.party_type == "Customer" else "is_internal_supplier"
    parties = frappe.get_list(
        doc.party_type,
        filters={internal_field: 1, "disabled": 0},
        pluck="name",
        order_by="name",
        limit=1,
    )
    return parties[0] if parties else None


def _fetch_isd_address(link_doctype, link_name, *, isd):
    """First enabled address of the owner, with the ISD / non-ISD gst_category as required."""
    if not link_name:
        return None

    results = frappe.get_list(
        "Address",
        filters=[
            ["disabled", "=", 0],
            ["Dynamic Link", "link_doctype", "=", link_doctype],
            ["Dynamic Link", "link_name", "=", link_name],
            ["gst_category", "=" if isd else "!=", ISD_GST_CATEGORY],
        ],
        pluck="name",
        order_by="is_primary_address DESC, name",
        limit=1,
    )
    return results[0] if results else None


def _resolve_isd_provisional_account(doc):
    if not doc.company:
        return None

    if not doc.is_against_party:
        return frappe.get_cached_value("Company", doc.company, "default_isd_provisional_account")

    if not doc.party_type:
        return None

    # leaf module: import lazily to avoid pulling erpnext at import time
    from erpnext.accounts.party import get_party_account

    return get_party_account(doc.party_type, doc.party, doc.company)


def _resolve_isd_addresses(doc, is_distribution_side):
    """Return (company_address, party_address)."""
    if not doc.company:
        return None, None

    # the company holds the ISD registration when distributing, the recipient one when receiving
    company_address = _fetch_isd_address("Company", doc.company, isd=is_distribution_side)

    if not doc.is_against_party:
        # single-company setup: the counterparty registration belongs to the company too
        return company_address, _fetch_isd_address("Company", doc.company, isd=not is_distribution_side)

    # counterparty side needs a party; still fill the company-owned side meanwhile
    party_address = None
    if doc.party_type and doc.party:
        party_address = _fetch_isd_address(doc.party_type, doc.party, isd=not is_distribution_side)

    return company_address, party_address


def _resolve_recipient_branch_turnover(doc):
    # only called on the distribution side, where the recipient is the party
    if not (doc.party_address and doc.company):
        return doc.branch_turnover

    gst_state = frappe.get_cached_value("Address", doc.party_address, "gst_state")

    return get_turnover_amount(doc.company, gst_state, doc.posting_date)


@frappe.whitelist()
def get_isd_autofill_values(doctype: str, changed_field: str, doc: str | dict):
    """Single-call autofill for both ISD doctypes"""
    if doctype not in ISD_DOCTYPES:
        frappe.throw(_("{0} is not an ISD doctype").format(doctype))

    frappe.has_permission(doctype, throw=True)

    doc = frappe._dict(frappe.parse_json(doc))
    doc.is_against_party = cint(doc.is_against_party)
    is_distribution_side = doctype == "ISD Distribution Invoice"

    if doc.company:
        frappe.has_permission("Company", doc=doc.company, throw=True)

    values = frappe._dict()

    if changed_field in _PARTY_CHAIN:
        downstream = _PARTY_CHAIN[_PARTY_CHAIN.index(changed_field) + 1 :]
        if "party_type" in downstream:
            values.party_type = doc.party_type = _resolve_isd_party_type(doc, is_distribution_side)
        if "party" in downstream:
            values.party = doc.party = _resolve_isd_party(doc)

        values.isd_provisional_account = _resolve_isd_provisional_account(doc)
        company_address, party_address = _resolve_isd_addresses(doc, is_distribution_side)

        values.party_address = doc.party_address = party_address
        # the company-owned address only changes when the company itself changes
        if changed_field == "company":
            values.company_address = doc.company_address = company_address

    if is_distribution_side:
        values.branch_turnover = _resolve_recipient_branch_turnover(doc)

    return values


# ---------------------------------------------------------------------------- bulk distribution dialog
@frappe.whitelist()
def get_distribution_addresses(
    party_type: str, party: str, company: str, pi_posting_date: str, address: str | None = None
):
    """For distribution addresses table in bulk distribution dialog"""

    if not party_type or not party:
        frappe.throw(_("Party Type and Party are mandatory"))

    frappe.has_permission(party_type, doc=party, ptype="read", throw=True)
    frappe.has_permission("Address", ptype="read", throw=True)

    fy_from, fy_to = get_relevant_period(pi_posting_date)

    addr = frappe.qb.DocType("Address")
    dynamic_link = frappe.qb.DocType("Dynamic Link")
    turnover_record = frappe.qb.DocType("Turnover Record")

    query = (
        frappe.qb.from_(addr)
        .join(dynamic_link)
        .on(dynamic_link.parent == addr.name)
        .left_join(turnover_record)
        .on(
            (turnover_record.company == company)
            & (IfNull(turnover_record.gst_state, "") == IfNull(addr.gst_state, ""))
            & (turnover_record.from_date <= fy_to)
            & (turnover_record.to_date >= fy_from)
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

    return {"addresses": query.run(as_dict=True), "relevant_period": [fy_from, fy_to]}


@frappe.whitelist()
def get_purchase_invoice_distribution_summary(purchase_invoice: str):
    frappe.has_permission("Purchase Invoice", "read", doc=purchase_invoice, throw=True)

    pi_item = frappe.qb.DocType("Purchase Invoice Item")
    total_tax = flt(
        (
            frappe.qb.from_(pi_item)
            .where(pi_item.parent == purchase_invoice)
            .select(reduce(add, (Coalesce(Sum(getattr(pi_item, f"{t}_amount")), 0) for t in GST_TAX_TYPES)))
            .run()
        )[0][0]
    )

    isd_source_item = frappe.qb.DocType("ISD Source Item")
    isd_invoice = frappe.qb.DocType("ISD Distribution Invoice")
    distributed_tax = flt(
        (
            frappe.qb.from_(isd_source_item)
            .join(isd_invoice)
            .on(isd_source_item.parent == isd_invoice.name)
            .where(isd_invoice.purchase_invoice == purchase_invoice)
            .where(isd_invoice.docstatus == 1)
            .select(
                reduce(
                    add,
                    (Coalesce(Sum(getattr(isd_source_item, f"distributed_{t}")), 0) for t in GST_TAX_TYPES),
                )
            )
            .run()
        )[0][0]
    )

    posting_date, supplier = frappe.db.get_value(
        "Purchase Invoice", purchase_invoice, ["posting_date", "supplier"]
    )

    return {
        "purchase_invoice": purchase_invoice,
        "posting_date": posting_date,
        "supplier": supplier,
        "total_tax": total_tax,
        "distributed_tax": distributed_tax,
        "available_tax": total_tax - distributed_tax,
    }


@frappe.whitelist()
def bulk_create_isd_distribution_invoices(
    purchase_invoice: str,
    distribution_table: list | str,
    posting_date: str,
    total_turnover: float | str,
):
    frappe.has_permission("ISD Distribution Invoice", "create", throw=True)
    frappe.has_permission("Purchase Invoice", "read", doc=purchase_invoice, throw=True)

    if isinstance(distribution_table, str):
        distribution_table = frappe.parse_json(distribution_table)
    posting_date = getdate(posting_date)

    distribution_table = [row for row in distribution_table if flt(row.get("turnover_amount"))]
    if not distribution_table:
        frappe.throw(_("No rows with turnover to distribute."))

    total_turnover = flt(total_turnover)
    if total_turnover <= 0:
        frappe.throw(_("Total Turnover must be greater than zero."))

    pi = get_purchase_doc(purchase_invoice)

    invoices, failed = [], []
    turnover_data = []
    for row in distribution_table:
        party_type = row.get("party_type")
        is_against_party = 1 if party_type and party_type != "Company" and row.get("party") else 0
        turnover = flt(row["turnover_amount"])

        doc = frappe.new_doc("ISD Distribution Invoice")
        doc.update(
            {
                "company": pi.company,
                "posting_date": posting_date,
                "purchase_invoice": pi.name,
                "company_address": pi.billing_address,
                "party_address": row.get("address"),
                "is_against_party": is_against_party,
                "party_type": party_type if is_against_party else None,
                "party": row.get("party") if is_against_party else None,
                "branch_turnover": turnover,
                "total_turnover": total_turnover,
                "distribution_ratio": flt(turnover / total_turnover * 100) if total_turnover else 0,
                "is_credit_note": cint(pi.is_return),
            }
        )
        doc.extend("source_items", [dict(item) for item in pi.source_items])

        turnover_data.append((pi.company, row.get("gstin"), row.get("gst_state"), turnover, pi.posting_date))

        frappe.db.savepoint("isd_bulk")
        try:
            doc.insert()
        except Exception:
            # one unsavable row must not take the invoices already created down with it
            frappe.db.rollback(save_point="isd_bulk")
            frappe.log_error(
                title=_("Bulk ISD Distribution Invoice creation failed for {0}").format(row.get("address"))
            )
            failed.append(row.get("address"))
            continue

        invoices.append(doc.name)

    frappe.enqueue(
        "india_compliance.gst_india.utils.isd._upsert_turnover_records",
        data=turnover_data,
        enqueue_after_commit=True,
    )

    return {"invoices": invoices, "failed": failed}


def _upsert_turnover_records(data):
    """Data = [(company, gstin, gst_state, turnover, posting_date), ...]"""
    for company, gstin, gst_state, turnover, date in data:
        upsert_turnover_record(
            company=company,
            gstin=gstin,
            gst_state=gst_state,
            amount=turnover,
            posting_date=date,
        )
