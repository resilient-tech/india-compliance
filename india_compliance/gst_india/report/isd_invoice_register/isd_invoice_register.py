# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.core.doctype.user_permission.user_permission import get_permitted_documents
from frappe.query_builder import Order
from frappe.query_builder.functions import Sum
from pypika.terms import Case


def execute(filters=None):
    validate_filters(filters)
    filters = frappe._dict(filters or {})
    columns = get_columns(filters)
    data = get_data(filters)
    return columns, data


def validate_filters(filters=None):
    if not filters:
        filters = {}
    filters = frappe._dict(filters)

    if filters.company:
        frappe.has_permission("Company", doc=filters.company, throw=True)

    if not filters.from_date or not filters.to_date:
        frappe.throw(
            _("From Date & To Date is mandatory for generating ISD Invoice Register"),
            title=_("Invalid Filter"),
        )
    if filters.from_date > filters.to_date:
        frappe.throw(_("From Date must be before To Date"), title=_("Invalid Filter"))


def get_data(filters):
    if filters.report_view == "Purchase Invoice":
        return get_purchase_invoice_data(filters)
    else:
        return get_isd_invoice_data(filters)


# ── View A: Purchase Invoice ──────────────────────────────────────────────────


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
        .when(pi.company_gstin[0:2] == pi.place_of_supply[0:2], "Intra-State")
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
            Sum(pi_item.igst_amount).as_("igst_amount"),
            Sum(pi_item.cgst_amount).as_("cgst_amount"),
            Sum(pi_item.sgst_amount).as_("sgst_amount"),
            Sum(pi_item.cess_amount).as_("cess_amount"),
            Sum(pi_item.cess_non_advol_amount).as_("cess_non_advol_amount"),
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

    if filters.get("company"):
        query = query.where(pi.company == filters.company)
    else:
        permitted = get_permitted_documents("Company")
        if permitted:
            query = query.where(pi.company.isin(permitted))

    if filters.get("company_gstin"):
        query = query.where(pi.company_gstin == filters.company_gstin)

    if filters.get("supplier"):
        query = query.where(pi.supplier == filters.supplier)

    return query.run(as_dict=True)


# ── View B: ISD Invoice ───────────────────────────────────────────────────────


def get_isd_invoice_data(filters):
    isd = frappe.qb.DocType("ISD Invoice")
    isd_src_items = frappe.qb.DocType("ISD Invoice Source Item")

    dist_igst = Sum(isd_src_items.distributed_igst).as_("distributed_igst")
    dist_cgst = Sum(isd_src_items.distributed_cgst).as_("distributed_cgst")
    dist_sgst = Sum(isd_src_items.distributed_sgst).as_("distributed_sgst")
    dist_cess = Sum(isd_src_items.distributed_cess).as_("distributed_cess")
    dist_cess_non_advol = Sum(isd_src_items.distributed_cess_non_advol).as_("distributed_cess_non_advol")

    # credit_flow='Credit Distribution' → company is distributor, party is recipient
    # credit_flow='Credit Receipt'  → party is distributor, company is recipient
    distributor_gstin_col = (
        Case()
        .when(isd.credit_flow == "Credit Distribution", isd.company_gstin)
        .else_(isd.party_gstin)
        .as_("distributor_gstin")
    )
    recipient_gstin_col = (
        Case()
        .when(isd.credit_flow == "Credit Distribution", isd.party_gstin)
        .else_(isd.company_gstin)
        .as_("recipient_gstin")
    )

    query = (
        frappe.qb.from_(isd)
        .left_join(isd_src_items)
        .on(isd_src_items.parent == isd.name)
        .select(
            isd.name.as_("isd_invoice"),
            isd.posting_date,
            distributor_gstin_col,
            recipient_gstin_col,
            isd.party_pos.as_("recipient_pos"),
            isd.is_credit_note,
            Case()
            .when(isd_src_items.is_ineligible_for_itc == 0, "Eligible")
            .else_("Ineligible")
            .as_("eligibility"),
            dist_igst,
            dist_cgst,
            dist_sgst,
            dist_cess,
            dist_cess_non_advol,
        )
        .where(isd.docstatus == 1)
        .where(isd.posting_date[filters.from_date : filters.to_date])
        .groupby(isd.name, isd_src_items.is_ineligible_for_itc)
        .orderby(isd.posting_date, order=Order.desc)
        .orderby(isd.name, order=Order.asc)
    )

    if filters.get("company"):
        query = query.where(isd.company == filters.company)
    else:
        permitted = get_permitted_documents("Company")
        if permitted:
            query = query.where(isd.company.isin(permitted))

    if filters.get("distributor_gstin"):
        query = query.where(
            Case().when(isd.credit_flow == "Credit Distribution", isd.company_gstin).else_(isd.party_gstin)
            == filters.distributor_gstin
        )

    if filters.get("recipient_gstin"):
        query = query.where(
            Case().when(isd.credit_flow == "Credit Distribution", isd.party_gstin).else_(isd.company_gstin)
            == filters.recipient_gstin
        )

    if filters.get("recipient_state"):
        query = query.where(isd.party_pos == filters.recipient_state)

    if filters.get("is_credit_note_only"):
        query = query.where(isd.is_credit_note == 1)

    return query.run(as_dict=True)


# ── Columns ───────────────────────────────────────────────────────────────────


def get_columns(filters):
    report_view = filters.get("report_view", "Purchase Invoice")
    company_currency = (
        frappe.get_cached_value("Company", filters.company, "default_currency")
        if filters.get("company")
        else frappe.db.get_default("currency") or "INR"
    )

    if report_view == "Purchase Invoice":
        return _get_purchase_invoice_columns(company_currency)
    else:
        return _get_isd_invoice_columns(company_currency)


def _get_purchase_invoice_columns(company_currency):
    return [
        {
            "fieldname": "company_gstin",
            "label": _("Company GSTIN"),
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "fieldname": "supplier_gstin",
            "label": _("Supplier GSTIN"),
            "fieldtype": "Data",
            "width": 150,
        },
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
        {
            "fieldname": "invoice_date",
            "label": _("Invoice Date"),
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "fieldname": "pos",
            "label": _("POS"),
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "fieldname": "total_invoice_value",
            "label": _("Total Invoice Value"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 150,
        },
        {
            "fieldname": "supply_type",
            "label": _("Supply Type"),
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "fieldname": "is_return",
            "label": _("Is Return"),
            "fieldtype": "Check",
            "width": 100,
        },
        {
            "fieldname": "rate",
            "label": _("Rate (%)"),
            "fieldtype": "Percent",
            "width": 90,
        },
        {
            "fieldname": "taxable_value",
            "label": _("Taxable Value"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 130,
        },
        {
            "fieldname": "igst_amount",
            "label": _("IGST"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 110,
        },
        {
            "fieldname": "cgst_amount",
            "label": _("CGST"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 110,
        },
        {
            "fieldname": "sgst_amount",
            "label": _("SGST"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 110,
        },
        {
            "fieldname": "cess_amount",
            "label": _("Cess"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 110,
        },
        {
            "fieldname": "cess_non_advol_amount",
            "label": _("Cess Non-Advol"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 120,
        },
    ]


def _get_isd_invoice_columns(company_currency):
    return [
        {
            "fieldname": "distributor_gstin",
            "label": _("Distributor GSTIN"),
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "recipient_gstin",
            "label": _("Recipient GSTIN"),
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "recipient_pos",
            "label": _("Recipient POS"),
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "fieldname": "isd_invoice",
            "label": _("ISD Invoice"),
            "fieldtype": "Link",
            "options": "ISD Invoice",
            "width": 180,
            "sticky": True,
        },
        {
            "fieldname": "posting_date",
            "label": _("Date"),
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "fieldname": "is_credit_note",
            "label": _("Is Credit Note"),
            "fieldtype": "Check",
            "width": 100,
        },
        {
            "fieldname": "eligibility",
            "label": _("Eligibility"),
            "fieldtype": "Data",
            "width": 110,
        },
        {
            "fieldname": "distributed_igst",
            "label": _("IGST"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 100,
        },
        {
            "fieldname": "distributed_cgst",
            "label": _("CGST"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 100,
        },
        {
            "fieldname": "distributed_sgst",
            "label": _("SGST"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 100,
        },
        {
            "fieldname": "distributed_cess",
            "label": _("Cess"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 100,
        },
        {
            "fieldname": "distributed_cess_non_advol",
            "label": _("Cess Non-Advol"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 120,
        },
    ]
