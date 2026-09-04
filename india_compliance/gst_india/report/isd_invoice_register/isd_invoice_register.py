# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from erpnext import get_company_currency
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder.functions import Substring, Sum
from pypika.terms import Case

from india_compliance.gst_india.constants import IMPORT_GST_CATEGORIES, STATE_NUMBERS
from india_compliance.gst_india.utils import validate_common_report_filters

DISTRIBUTION_DOCTYPE = "ISD Distribution Invoice"
RECIPIENT_DOCTYPE = "ISD Recipient Invoice"
SOURCE_ITEM_DOCTYPE = "ISD Source Item"


def get_pos_for_state(state):
    state_number = STATE_NUMBERS.get(state)
    if not state_number:
        frappe.throw(_("{0} is not a valid State").format(frappe.bold(state)), title=_("Invalid Filter"))

    return f"{state_number}-{state}"


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if filters.get("date_range"):
        filters.from_date, filters.to_date = filters.date_range
    validate_common_report_filters(filters)
    columns = get_columns(filters)
    data = get_data(filters)
    return columns, data


def get_data(filters):
    report_view = filters.get("report_view", "Purchase Invoice")
    if report_view == "ISD Distribution Invoice":
        return get_distribution_invoice_data(filters)

    if report_view == "ISD Recipient Invoice":
        return get_recipient_invoice_data(filters)

    return get_purchase_invoice_data(filters)


# ── View A: Purchase Invoice (available ITC pool) ─────────────────────────────


def get_purchase_invoice_data(filters):
    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")

    rate = (
        pi_item.igst_rate
        + pi_item.cgst_rate
        + pi_item.sgst_rate
        + pi_item.cess_rate
        + pi_item.cess_non_advol_rate
    ).as_("rate")

    supply_type = (
        Case()
        .when(pi.gst_category.isin(IMPORT_GST_CATEGORIES), "Inter-State")
        .when(Substring(pi.supplier_gstin, 1, 2) == Substring(pi.place_of_supply, 1, 2), "Intra-State")
        .else_("Inter-State")
        .as_("supply_type")
    )

    query = (
        frappe.qb.from_(pi)
        .join(pi_item)
        .on(pi_item.parent == pi.name)
        .select(
            pi.company_gstin,
            pi.supplier_gstin,
            pi.supplier,
            pi.name.as_("invoice_name"),
            pi.posting_date.as_("invoice_date"),
            pi.place_of_supply.as_("pos"),
            pi.base_grand_total.as_("total_invoice_value"),
            supply_type,
            pi.is_return,
            rate,
            Sum(pi_item.net_amount).as_("taxable_value"),
            Sum(pi_item.cgst_amount).as_("cgst_amount"),
            Sum(pi_item.sgst_amount).as_("sgst_amount"),
            Sum(pi_item.igst_amount).as_("igst_amount"),
            (Sum(pi_item.cess_amount) + Sum(pi_item.cess_non_advol_amount)).as_("cess_amount"),
        )
        .where(pi.docstatus == 1)
        .where(pi.is_isd_applicable == 1)
        .where(pi.posting_date[filters.from_date : filters.to_date])
        .groupby(
            pi.name,
            pi_item.igst_rate
            + pi_item.cgst_rate
            + pi_item.sgst_rate
            + pi_item.cess_rate
            + pi_item.cess_non_advol_rate,
        )
        .orderby(pi.posting_date, order=Order.desc)
        .orderby(pi.name, order=Order.asc)
    )

    query = query.where(pi.company == filters.company)

    if filters.get("company_gstin"):
        query = query.where(pi.company_gstin == filters.company_gstin)

    if filters.get("supplier"):
        query = query.where(pi.supplier == filters.supplier)

    if filters.get("purchase_invoice"):
        query = query.where(pi.name == filters.purchase_invoice)

    if filters.get("is_return"):
        query = query.where(pi.is_return == 1)

    return query.run(as_dict=True)


# ── View B: ISD Distribution Invoice (head-office / distributor side) ──────────


def get_distribution_invoice_data(filters):
    """One row per (Distribution Invoice x eligibility): the ITC available on the source purchase
    invoice and the amount distributed by the head office (converted heads -- IGST-only when
    inter-state)."""
    dist = frappe.qb.DocType(DISTRIBUTION_DOCTYPE)
    src = frappe.qb.DocType(SOURCE_ITEM_DOCTYPE)

    query = (
        frappe.qb.from_(dist)
        .left_join(src)
        .on((src.parent == dist.name) & (src.parenttype == DISTRIBUTION_DOCTYPE))
        .select(
            dist.name.as_("isd_distribution_invoice"),
            dist.purchase_invoice,
            dist.posting_date,
            dist.company_gstin,
            dist.party_gstin,
            dist.party_pos,
            dist.is_credit_note,
            src.is_ineligible_for_itc,
            Case().when(src.is_ineligible_for_itc == 0, "Eligible").else_("Ineligible").as_("eligibility"),
            Sum(src.total_igst).as_("total_igst"),
            Sum(src.total_cgst).as_("total_cgst"),
            Sum(src.total_sgst).as_("total_sgst"),
            (Sum(src.total_cess) + Sum(src.total_cess_non_advol)).as_("total_cess"),
            Sum(src.total_expense).as_("total_expense"),
            Sum(src.distributed_igst).as_("distributed_igst"),
            Sum(src.distributed_cgst).as_("distributed_cgst"),
            Sum(src.distributed_sgst).as_("distributed_sgst"),
            (Sum(src.distributed_cess) + Sum(src.distributed_cess_non_advol)).as_("distributed_cess"),
            Sum(src.distributed_expense).as_("distributed_expense"),
        )
        .where(dist.docstatus == 1)
        .where(dist.posting_date[filters.from_date : filters.to_date])
        .groupby(dist.name, src.is_ineligible_for_itc)
        .orderby(dist.posting_date, order=Order.desc)
        .orderby(dist.name, order=Order.asc)
    )

    query = query.where(dist.company == filters.company)

    if filters.get("company_gstin"):
        query = query.where(dist.company_gstin == filters.company_gstin)

    if filters.get("party_gstin"):
        query = query.where(dist.party_gstin == filters.party_gstin)

    if filters.get("recipient_state"):
        query = query.where(dist.party_pos == get_pos_for_state(filters.recipient_state))

    if filters.get("is_credit_note"):
        query = query.where(dist.is_credit_note == 1)

    return query.run(as_dict=True)


# ── View C: ISD Recipient Invoice (branch / recipient side) ───────────────────


def get_recipient_invoice_data(filters):
    """One row per (Recipient Invoice x eligibility): the ITC received on the branch side (converted
    heads). Includes recipient invoices booked against an external ISD (no internal distribution
    invoice reference), which carry `external_isd_invoice_number` instead."""
    rec = frappe.qb.DocType(RECIPIENT_DOCTYPE)
    src = frappe.qb.DocType(SOURCE_ITEM_DOCTYPE)

    query = (
        frappe.qb.from_(rec)
        .left_join(src)
        .on((src.parent == rec.name) & (src.parenttype == RECIPIENT_DOCTYPE))
        .select(
            rec.name.as_("isd_recipient_invoice"),
            rec.posting_date,
            rec.party_gstin,
            rec.company_gstin,
            rec.company_pos,
            rec.isd_distribution_invoice_reference,
            rec.external_isd_invoice_number,
            rec.is_credit_note,
            src.is_ineligible_for_itc,
            Case().when(src.is_ineligible_for_itc == 0, "Eligible").else_("Ineligible").as_("eligibility"),
            Sum(src.distributed_igst).as_("recipient_igst"),
            Sum(src.distributed_cgst).as_("recipient_cgst"),
            Sum(src.distributed_sgst).as_("recipient_sgst"),
            (Sum(src.distributed_cess) + Sum(src.distributed_cess_non_advol)).as_("recipient_cess"),
            Sum(src.distributed_expense).as_("recipient_expense"),
        )
        .where(rec.docstatus == 1)
        .where(rec.posting_date[filters.from_date : filters.to_date])
        .groupby(rec.name, src.is_ineligible_for_itc)
        .orderby(rec.posting_date, order=Order.desc)
        .orderby(rec.name, order=Order.asc)
    )

    query = query.where(rec.company == filters.company)

    if filters.get("company_gstin"):
        query = query.where(rec.company_gstin == filters.company_gstin)

    if filters.get("party_gstin"):
        query = query.where(rec.party_gstin == filters.party_gstin)

    if filters.get("recipient_state"):
        query = query.where(rec.company_pos == get_pos_for_state(filters.recipient_state))

    if filters.get("is_credit_note"):
        query = query.where(rec.is_credit_note == 1)

    return query.run(as_dict=True)


# ── Columns ───────────────────────────────────────────────────────────────────


def get_columns(filters):
    report_view = filters.get("report_view", "Purchase Invoice")
    company_currency = get_company_currency(filters.company)

    if report_view == "ISD Distribution Invoice":
        return _get_distribution_invoice_columns(company_currency)

    if report_view == "ISD Recipient Invoice":
        return _get_recipient_invoice_columns(company_currency)

    return _get_purchase_invoice_columns(company_currency)


def _currency_column(fieldname, label, company_currency, width=120):
    return {
        "fieldname": fieldname,
        "label": _(label),
        "fieldtype": "Currency",
        "options": company_currency,
        "width": width,
    }


def _get_purchase_invoice_columns(company_currency):
    return [
        {"fieldname": "company_gstin", "label": _("Company GSTIN"), "fieldtype": "Data", "width": 150},
        {"fieldname": "supplier_gstin", "label": _("Supplier GSTIN"), "fieldtype": "Data", "width": 150},
        {
            "fieldname": "supplier",
            "label": _("Supplier"),
            "fieldtype": "Link",
            "options": "Supplier",
            "width": 160,
        },
        {
            "fieldname": "invoice_name",
            "label": _("Invoice No"),
            "fieldtype": "Link",
            "options": "Purchase Invoice",
            "width": 160,
            "sticky": True,
        },
        {"fieldname": "invoice_date", "label": _("Invoice Date"), "fieldtype": "Date", "width": 120},
        {"fieldname": "pos", "label": _("POS"), "fieldtype": "Data", "width": 120},
        _currency_column("total_invoice_value", "Total Invoice Value", company_currency, 150),
        {"fieldname": "supply_type", "label": _("Supply Type"), "fieldtype": "Data", "width": 120},
        {"fieldname": "is_return", "label": _("Is Return"), "fieldtype": "Check", "width": 100},
        {"fieldname": "rate", "label": _("Rate (%)"), "fieldtype": "Percent", "width": 90},
        _currency_column("taxable_value", "Taxable Value", company_currency, 130),
        _currency_column("igst_amount", "IGST", company_currency, 110),
        _currency_column("cgst_amount", "CGST", company_currency, 110),
        _currency_column("sgst_amount", "SGST", company_currency, 110),
        _currency_column("cess_amount", "Cess", company_currency, 110),
    ]


def _get_distribution_invoice_columns(company_currency):
    return [
        {
            "fieldname": "company_gstin",
            "label": _("Distributor GSTIN"),
            "fieldtype": "Data",
            "width": 180,
        },
        {"fieldname": "party_gstin", "label": _("Recipient GSTIN"), "fieldtype": "Data", "width": 180},
        {"fieldname": "party_pos", "label": _("Recipient POS"), "fieldtype": "Data", "width": 130},
        {
            "fieldname": "isd_distribution_invoice",
            "label": _("ISD Distribution Invoice"),
            "fieldtype": "Link",
            "options": DISTRIBUTION_DOCTYPE,
            "width": 200,
            "sticky": True,
        },
        {
            "fieldname": "purchase_invoice",
            "label": _("Purchase Invoice"),
            "fieldtype": "Link",
            "options": "Purchase Invoice",
            "width": 180,
        },
        {"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "is_credit_note", "label": _("Is Credit Note"), "fieldtype": "Check", "width": 100},
        {"fieldname": "eligibility", "label": _("Eligibility"), "fieldtype": "Data", "width": 100},
        # Source ITC on the purchase invoice (pre-conversion heads).
        _currency_column("total_igst", "Available IGST", company_currency),
        _currency_column("total_cgst", "Available CGST", company_currency),
        _currency_column("total_sgst", "Available SGST", company_currency),
        _currency_column("total_cess", "Available Cess", company_currency),
        _currency_column("total_expense", "Available Expense", company_currency, 140),
        # Distributed by the head office (converted heads: IGST-only when inter-state).
        _currency_column("distributed_igst", "Distributed IGST", company_currency, 130),
        _currency_column("distributed_cgst", "Distributed CGST", company_currency, 130),
        _currency_column("distributed_sgst", "Distributed SGST", company_currency, 130),
        _currency_column("distributed_cess", "Distributed Cess", company_currency, 130),
        _currency_column("distributed_expense", "Distributed Expense", company_currency, 150),
    ]


def _get_recipient_invoice_columns(company_currency):
    return [
        {
            "fieldname": "party_gstin",
            "label": _("Distribution GSTIN"),
            "fieldtype": "Data",
            "width": 180,
        },
        {"fieldname": "company_gstin", "label": _("Recipient GSTIN"), "fieldtype": "Data", "width": 180},
        {"fieldname": "company_pos", "label": _("Recipient POS"), "fieldtype": "Data", "width": 130},
        {
            "fieldname": "isd_recipient_invoice",
            "label": _("ISD Recipient Invoice"),
            "fieldtype": "Link",
            "options": RECIPIENT_DOCTYPE,
            "width": 200,
            "sticky": True,
        },
        {
            "fieldname": "isd_distribution_invoice_reference",
            "label": _("Distribution Invoice Ref"),
            "fieldtype": "Link",
            "options": DISTRIBUTION_DOCTYPE,
            "width": 200,
        },
        {
            "fieldname": "external_isd_invoice_number",
            "label": _("External ISD Invoice No"),
            "fieldtype": "Data",
            "width": 180,
        },
        {"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "is_credit_note", "label": _("Is Credit Note"), "fieldtype": "Check", "width": 100},
        {"fieldname": "eligibility", "label": _("Eligibility"), "fieldtype": "Data", "width": 100},
        # Received on the recipient invoice (converted heads: IGST-only when inter-state).
        _currency_column("recipient_igst", "Received IGST", company_currency, 130),
        _currency_column("recipient_cgst", "Received CGST", company_currency, 130),
        _currency_column("recipient_sgst", "Received SGST", company_currency, 130),
        _currency_column("recipient_cess", "Received Cess", company_currency, 130),
        _currency_column("recipient_expense", "Received Expense", company_currency, 150),
    ]
