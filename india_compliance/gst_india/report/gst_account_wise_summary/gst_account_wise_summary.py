# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import IfNull, Sum
from frappe.utils import flt

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.income_tax_india.overrides.tax_withholding_category import (
    get_tax_withholding_accounts,
)


def execute(filters: dict | None = None):
    filters = frappe._dict(filters or {})
    filters.from_date, filters.to_date = filters.date_range

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def get_columns():
    return [
        {
            "label": _("Account Name"),
            "fieldname": "account_name",
            "fieldtype": "Data",
            "width": 300,
        },
        {
            "label": _("Total Amount"),
            "fieldname": "total_amount",
            "fieldtype": "Float",
            "width": 200,
        },
        {
            "label": _("Amount of Total ITC"),
            "fieldname": "total_itc",
            "fieldtype": "Float",
            "width": 200,
        },
        {
            "label": _("Amount of eligible ITC availed"),
            "fieldname": "total_itc_availed",
            "fieldtype": "Float",
            "width": 250,
        },
    ]


def get_data(filters):
    account_summary = {}
    invoices = get_invoices(filters)
    tds_accounts = get_tax_withholding_accounts(filters.company)

    for invoice in invoices:
        additional_charges = 0
        additional_tax = 0
        eligible_items = 0

        for item in invoice["items"]:
            net_amount = item.base_net_amount
            account = item.expense_account
            account_data = account_summary.setdefault(account, defaultdict(float))
            account_data["account_name"] = account

            account_data["total_amount"] += net_amount

            proportional_tax = net_amount * (item.tax_rate / 100)
            account_data["total_itc"] += proportional_tax
            if not item.is_ineligible_for_itc:
                account_data["total_itc_availed"] += proportional_tax
                eligible_items += 1

            if invoice.doctype == "Bill of Entry":
                continue

            additional_charges += item.taxable_value - net_amount
            additional_tax += item.tax_amount - proportional_tax

        if not additional_charges:
            continue

        proportion = additional_tax / additional_charges
        eligibility_proportion = (eligible_items / len(invoice["items"])) * proportion

        if not eligibility_proportion:
            continue

        additional_tax /= eligibility_proportion

        # Filter required taxes
        taxes = []
        for tax in invoice["taxes"]:
            if tax.gst_tax_type in GST_TAX_TYPES:
                break
            elif tax.account_head in tds_accounts:
                continue

            taxes.append(tax)

        for i, tax in enumerate(taxes):
            tax_amount = tax.base_tax_amount_after_discount_amount
            account = tax.account_head
            account_data = account_summary.setdefault(account, defaultdict(float))
            account_data["account_name"] = account

            # Calculate proportional ITC for this tax
            if i == len(taxes) - 1:
                # For the last item, adjust to ensure total matches additional_tax
                itc_amount = flt(additional_tax, 2)
            else:
                itc_amount = tax_amount * eligibility_proportion
                additional_tax -= itc_amount
                itc_amount = flt(itc_amount, 2)

            account_data["total_amount"] += tax_amount
            account_data["total_itc"] += itc_amount

    account_summary_data = list(account_summary.values())

    if filters.voucher_type == "Purchase" and (
        ineligible_itc_from_je := get_ineligible_itc_from_je(filters)
    ):
        account_summary_data.append(ineligible_itc_from_je)

    return account_summary_data


def get_invoices(filters):
    if filters.voucher_type == "Sales":
        doctypes = ["Sales Invoice"]
        filters["gstin_field"] = "billing_address_gstin"
    else:
        doctypes = ["Purchase Invoice", "Bill of Entry"]
        filters["gstin_field"] = "supplier_gstin"

    compiled_docs = frappe._dict()
    for doctype in doctypes:
        filters.doctype = doctype
        taxes = get_taxes_for_docs(filters)
        items = get_items_for_docs(filters)

        compile_docs(taxes, items, filters.doctype, compiled_docs)

    return list(compiled_docs.values())


def get_taxes_for_docs(filters):
    if filters.doctype == "Bill of Entry":
        return []

    taxes_doctype = (
        "Sales Taxes and Charges"
        if filters.doctype == "Sales Invoice"
        else "Purchase Taxes and Charges"
    )

    doc = frappe.qb.DocType(filters.doctype)
    taxes_doc = frappe.qb.DocType(taxes_doctype)

    query = (
        frappe.qb.from_(doc)
        .join(taxes_doc)
        .on((doc.name == taxes_doc.parent) & (taxes_doc.parenttype == filters.doctype))
        .select(
            taxes_doc.tax_amount,
            taxes_doc.base_tax_amount_after_discount_amount,
            taxes_doc.gst_tax_type,
            taxes_doc.parent,
            taxes_doc.account_head,
            taxes_doc.charge_type,
        )
        .orderby(taxes_doc.idx)
    )

    query = get_query_with_common_filters(query, doc, filters)

    return query.run(as_dict=True)


def get_items_for_docs(filters):
    if filters.doctype == "Bill of Entry":
        return get_items_for_boe_docs(filters)

    doc = frappe.qb.DocType(filters.doctype)
    item_doc = frappe.qb.DocType(f"{filters.doctype} Item")

    query = (
        frappe.qb.from_(doc)
        .join(item_doc)
        .on((doc.name == item_doc.parent) & (item_doc.parenttype == filters.doctype))
        .select(
            item_doc.name,
            item_doc.parent,
            item_doc.expense_account,
            item_doc.item_code,
            item_doc.item_name,
            item_doc.qty,
            item_doc.taxable_value,
            item_doc.base_net_amount,
            (item_doc.cgst_rate + item_doc.sgst_rate + item_doc.igst_rate).as_(
                "tax_rate"
            ),
            (
                item_doc.cgst_amount
                + item_doc.sgst_amount
                + item_doc.igst_amount
                + item_doc.cess_amount
                + item_doc.cess_non_advol_amount
            ).as_("tax_amount"),
        )
    )

    if filters.doctype == "Purchase Invoice":
        query = query.select(
            Case("is_ineligible_for_itc")
            .when(item_doc.is_ineligible_for_itc == 1, 1)
            .when(doc.ineligibility_reason == "ITC restricted due to PoS rules", 1)
            .else_(0)
        ).where(
            Case()
            .when(doc.gst_category == "Overseas", item_doc.pending_boe_qty > 0)
            .else_(1)
        )

    query = get_query_with_common_filters(query, doc, filters)

    return query.run(as_dict=True)


def get_items_for_boe_docs(filters):
    doc = frappe.qb.DocType(filters.doctype)
    item_doc = frappe.qb.DocType(f"{filters.doctype} Item")
    pinv_item = frappe.qb.DocType("Purchase Invoice Item")

    query = (
        frappe.qb.from_(doc)
        .join(item_doc)
        .on((doc.name == item_doc.parent) & (item_doc.parenttype == filters.doctype))
        .join(pinv_item)
        .on(item_doc.pi_detail == pinv_item.name)
        .select(
            item_doc.name,
            item_doc.parent,
            pinv_item.expense_account,
            item_doc.item_code,
            item_doc.item_name,
            item_doc.qty,
            item_doc.taxable_value.as_("base_net_amount"),
            (item_doc.cgst_rate + item_doc.sgst_rate + item_doc.igst_rate).as_(
                "tax_rate"
            ),
            (
                item_doc.cgst_amount
                + item_doc.sgst_amount
                + item_doc.igst_amount
                + item_doc.cess_amount
                + item_doc.cess_non_advol_amount
            ).as_("tax_amount"),
        )
    )

    query = get_query_with_common_filters(query, doc, filters)

    return query.run(as_dict=True)


def compile_docs(taxes, items, doctype, compiled_docs):
    """
    Compile docs, so that each one could be accessed as if it's a single doc.
    """
    for tax in taxes:
        if tax.parent not in compiled_docs:
            compiled_docs[tax.parent] = frappe._dict(
                taxes=[], items=[], doctype=doctype
            )

        compiled_docs[tax.parent]["taxes"].append(tax)

    for item in items:
        if item.parent not in compiled_docs:
            compiled_docs[item.parent] = frappe._dict(
                taxes=[], items=[], doctype=doctype
            )

        compiled_docs[item.parent]["items"].append(item)


def get_query_with_common_filters(query, doc, filters):
    query = query.where(
        (doc.docstatus == 1)
        & (doc.posting_date[filters.from_date : filters.to_date])
        & (doc.company == filters.company)
    )

    if filters.get("doctype") not in ["Journal Entry", "Bill of Entry"]:
        query = query.where(doc.company_gstin != IfNull(doc[filters.gstin_field], ""))

    if filters.get("doctype") != "Bill of Entry":
        query = query.where(doc.is_opening == "No")

    if filters.get("company_gstin"):
        query = query.where(doc.company_gstin == filters.company_gstin)

    return query


def get_ineligible_itc_from_je(filters):
    filters.doctype = "Journal Entry"
    je_doc = frappe.qb.DocType(filters.doctype)
    je_account = frappe.qb.DocType(f"{filters.doctype} Account")

    query = (
        frappe.qb.from_(je_doc)
        .join(je_account)
        .on(je_account.parent == je_doc.name)
        .select(
            Sum(
                Case()
                .when(
                    je_account.gst_tax_type.isin(GST_TAX_TYPES),
                    (
                        je_account.credit_in_account_currency
                        - je_account.debit_in_account_currency
                    ),
                )
                .else_(0)
            ).as_("ineligible_itc")
        )
        .where(je_doc.voucher_type == "Reversal of ITC")
    )

    query = get_query_with_common_filters(query, je_doc, filters)

    ineligible_itc = query.run(as_dict=True)[0].get("ineligible_itc")

    if ineligible_itc:
        return {
            "account_name": "Ineligible ITC from Journal Entry",
            "total_amount": 0,
            "total_itc": 0,
            "total_itc_availed": -1 * ineligible_itc,
        }
