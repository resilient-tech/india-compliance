# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import IfNull, Sum

from india_compliance.gst_india.constants import GST_TAX_TYPES, TAX_TYPES
from india_compliance.income_tax_india.overrides.tax_withholding_category import (
    get_tax_withholding_accounts,
)


def execute(filters: dict | None = None):
    filters = frappe._dict(filters or {})
    filters.from_date, filters.to_date = filters.date_range

    report = AccountWiseSummary(filters)

    columns = report.get_columns()
    data = report.get_data()
    # TODO: Overview vs Breakup

    return columns, data


class AccountWiseSummary:
    def __init__(self, filters):
        self.filters = filters
        self.tds_accounts = get_tax_withholding_accounts(filters.company)

    @staticmethod
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

    def get_data(self):
        self.account_summary = defaultdict(lambda: defaultdict(float))
        invoices = self.get_invoices()

        for invoice in invoices:
            additional_amount = 0
            additional_tax = 0

            eligible_amount = 0
            total_amount = 0

            for item in invoice["items"]:
                net_amount = item.base_net_amount
                account = item.expense_account
                account_data = self.account_summary[account]
                account_data["account_name"] = account

                account_data["total_amount"] += net_amount
                total_amount += net_amount

                net_tax = net_amount * (item.tax_rate / 100) + item.cess_amount
                account_data["total_itc"] += net_tax

                if not item.is_ineligible_for_itc:
                    eligible_amount += net_amount
                    account_data["total_itc_availed"] += net_tax

                # charges not supported in Bill of Entry
                if invoice.doctype == "Bill of Entry":
                    continue

                # charges as apportioned
                additional_amount += item.taxable_value - net_amount
                additional_tax += item.tax_amount - net_tax

            total_proportion = (
                additional_tax / additional_amount if additional_amount else 0
            )
            eligible_proportion = eligible_amount / total_amount if total_amount else 0

            self.allocate_additional_charges(
                invoice, additional_tax, total_proportion, eligible_proportion
            )

        account_summary_data = list(self.account_summary.values())

        if ineligible_itc_from_je := self.get_ineligible_itc_from_je():
            account_summary_data.append(ineligible_itc_from_je)

        return account_summary_data

    def allocate_additional_charges(
        self, invoice, additional_tax, total_proportion, eligible_proportion
    ):

        before_gst = []
        after_gst = []
        is_after_gst = False

        for tax in invoice["taxes"]:
            if tax.gst_tax_type in TAX_TYPES:
                is_after_gst = True
                continue

            elif (
                tax.account_head in self.tds_accounts
                or not tax.base_tax_amount_after_discount_amount
            ):
                continue

            if not is_after_gst:
                before_gst.append(tax)
            else:
                after_gst.append(tax)

        def _append_charges(tax):
            account = tax.account_head
            account_data = self.account_summary[account]
            account_data["account_name"] = account

            tax_amount = tax.base_tax_amount_after_discount_amount
            if tax.get("add_deduct_tax", "Add") == "Deduct":
                tax_amount *= -1

            account_data["total_amount"] += tax_amount

            return account_data, tax_amount

        # approtion the additional tax to charges
        for i, tax in enumerate(before_gst):
            account_data, tax_amount = _append_charges(tax)

            if i == len(before_gst) - 1:
                # For the last item, adjust to ensure total matches additional_tax
                itc_amount = additional_tax

            else:
                itc_amount = tax_amount * total_proportion
                additional_tax -= itc_amount

            account_data["total_itc"] += itc_amount
            account_data["total_itc_availed"] += itc_amount * eligible_proportion

        # additional charges only
        for tax in after_gst:
            _append_charges(tax)

    def get_ineligible_itc_from_je(self):
        if self.filters.voucher_type == "Purchase":
            return

        filters = frappe._dict({**self.filters, "doctype": "Journal Entry"})
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

        query = self.get_query_with_common_filters(query, je_doc, filters)

        result = query.run(as_dict=True)
        ineligible_itc = result[0].get("ineligible_itc") if result else 0

        if ineligible_itc:
            return {
                "account_name": "Ineligible ITC from Journal Entry",
                "total_amount": 0,
                "total_itc": 0,
                "total_itc_availed": -1 * ineligible_itc,
            }

    # QUERIES

    def get_invoices(self):
        if self.filters.voucher_type == "Sales":
            doctypes = ["Sales Invoice"]
            self.filters["gstin_field"] = "billing_address_gstin"
        else:
            doctypes = ["Purchase Invoice", "Bill of Entry"]
            self.filters["gstin_field"] = "supplier_gstin"

        compiled_docs = frappe._dict()
        for doctype in doctypes:
            self.filters.doctype = doctype
            taxes = self.get_taxes_for_docs()
            items = self.get_items_for_docs()

            compile_docs(taxes, items, self.filters.doctype, compiled_docs)

        return list(compiled_docs.values())

    def get_taxes_for_docs(self):
        if self.filters.doctype == "Bill of Entry":
            return []

        taxes_doctype = (
            "Sales Taxes and Charges"
            if self.filters.doctype == "Sales Invoice"
            else "Purchase Taxes and Charges"
        )

        doc = frappe.qb.DocType(self.filters.doctype)
        taxes_doc = frappe.qb.DocType(taxes_doctype)

        query = (
            frappe.qb.from_(doc)
            .join(taxes_doc)
            .on(
                (doc.name == taxes_doc.parent)
                & (taxes_doc.parenttype == self.filters.doctype)
            )
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

        if self.filters.doctype == "Purchase Invoice":
            query = query.select(taxes_doc.add_deduct_tax)

        query = self.get_query_with_common_filters(query, doc, self.filters)

        return query.run(as_dict=True)

    def get_items_for_docs(self):
        if self.filters.doctype == "Bill of Entry":
            return self.get_items_for_boe_docs()

        doc = frappe.qb.DocType(self.filters.doctype)
        item_doc = frappe.qb.DocType(f"{self.filters.doctype} Item")

        query = (
            frappe.qb.from_(doc)
            .join(item_doc)
            .on(
                (doc.name == item_doc.parent)
                & (item_doc.parenttype == self.filters.doctype)
            )
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
                    item_doc.cgst_amount + item_doc.sgst_amount + item_doc.igst_amount
                ).as_("tax_amount"),
                (item_doc.cess_amount + item_doc.cess_non_advol_amount).as_(
                    "cess_amount"
                ),
            )
        )

        if self.filters.doctype == "Purchase Invoice":
            query = query.select(
                Case("is_ineligible_for_itc")
                .when(item_doc.is_ineligible_for_itc == 1, 1)
                .when(doc.ineligibility_reason == "ITC restricted due to PoS rules", 1)
                .else_(0)
                # From BOE
            ).where(IfNull(doc.itc_classification, "") != "Import of Goods")

        query = self.get_query_with_common_filters(query, doc, self.filters)

        return query.run(as_dict=True)

    def get_items_for_boe_docs(self):
        doc = frappe.qb.DocType(self.filters.doctype)
        item_doc = frappe.qb.DocType(f"{self.filters.doctype} Item")
        pinv_item = frappe.qb.DocType("Purchase Invoice Item")

        query = (
            frappe.qb.from_(doc)
            .join(item_doc)
            .on(
                (doc.name == item_doc.parent)
                & (item_doc.parenttype == self.filters.doctype)
            )
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
                    item_doc.cgst_amount + item_doc.sgst_amount + item_doc.igst_amount
                ).as_("tax_amount"),
                (item_doc.cess_amount + item_doc.cess_non_advol_amount).as_(
                    "cess_amount"
                ),
            )
        )

        query = self.get_query_with_common_filters(query, doc, self.filters)

        return query.run(as_dict=True)

    @staticmethod
    def get_query_with_common_filters(query, doc, filters):
        query = query.where(
            (doc.docstatus == 1)
            & (doc.posting_date[filters.from_date : filters.to_date])
            & (doc.company == filters.company)
        )

        if filters.get("doctype") not in ["Journal Entry", "Bill of Entry"]:
            query = query.where(
                doc.company_gstin != IfNull(doc[filters.gstin_field], "")
            )

        if filters.get("doctype") != "Bill of Entry":
            query = query.where(doc.is_opening == "No")

        if filters.get("company_gstin"):
            query = query.where(doc.company_gstin == filters.company_gstin)

        return query


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
