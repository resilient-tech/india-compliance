# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

from pypika import Order
from pypika.terms import ValueWrapper

import frappe
from frappe.query_builder import Case
from frappe.query_builder.functions import Date, IfNull
from frappe.utils import getdate


class ITC04Query:
    def __init__(self, filters=None):
        """Initialize the ITC04Query with optional filters."""
        self.filters = frappe._dict(filters or {})

        self.ref_doc = frappe.qb.DocType("Dynamic Link")
        self.se = frappe.qb.DocType("Stock Entry")
        self.se_item = frappe.qb.DocType("Stock Entry Detail")
        self.sr = frappe.qb.DocType("Subcontracting Receipt")
        self.sr_item = frappe.qb.DocType("Subcontracting Receipt Item")
        self.se_doctype = ValueWrapper("Stock Entry")
        self.sr_doctype = ValueWrapper("Subcontracting Receipt")

    def get_base_query_table_4(self, doc, doc_item):
        """Construct the base query for Table-4."""
        item = frappe.qb.DocType("Item")

        query = (
            frappe.qb.from_(doc)
            .inner_join(doc_item)
            .on(doc.name == doc_item.parent)
            .left_join(item)
            .on(doc_item.item_code == item.name)
            .select(
                IfNull(doc_item.item_code, doc_item.item_name).as_("item_code"),
                doc_item.qty,
                doc_item.gst_hsn_code,
                doc.supplier,
                doc.name.as_("invoice_no"),
                doc.posting_date,
                doc.is_return,
                IfNull(doc.place_of_supply, "").as_("place_of_supply"),
                doc.base_grand_total.as_("invoice_total"),
                IfNull(doc_item.gst_treatment, "Not Defined").as_("gst_treatment"),
                (doc_item.cgst_rate + doc_item.sgst_rate + doc_item.igst_rate).as_(
                    "gst_rate"
                ),
                doc_item.taxable_value,
                doc_item.cgst_amount,
                doc_item.sgst_amount,
                doc_item.igst_amount,
                doc_item.cess_amount,
                doc_item.cess_non_advol_amount,
                (doc_item.cess_amount + doc_item.cess_non_advol_amount).as_(
                    "total_cess_amount"
                ),
                (
                    doc_item.cgst_amount
                    + doc_item.sgst_amount
                    + doc_item.igst_amount
                    + doc_item.cess_amount
                    + doc_item.cess_non_advol_amount
                ).as_("total_tax"),
                (
                    doc_item.taxable_value
                    + doc_item.cgst_amount
                    + doc_item.sgst_amount
                    + doc_item.igst_amount
                    + doc_item.cess_amount
                    + doc_item.cess_non_advol_amount
                ).as_("total_amount"),
                Case()
                .when(item.is_fixed_asset == 1, "Capital Goods")
                .else_("Inputs")
                .as_("item_type"),
            )
            .where(doc.docstatus == 1)
            .orderby(doc.name, order=Order.desc)
        )
        query = self.get_query_with_common_filters(query, doc)

        return query

    def get_query_table_4_se(self):
        """
        Construct the query for Table-4 Stock Entry.
        - Table-4 is for goods sent to job worker.
        - This query is for Stock Entry with purpose "Send to Subcontractor".
        """

        query = (
            self.get_base_query_table_4(self.se, self.se_item)
            .select(
                self.se_item.uom,
                self.se.bill_to_gstin.as_("supplier_gstin"),
                self.se.bill_from_gstin.as_("company_gstin"),
                self.se_doctype.as_("invoice_type"),
            )
            .where(IfNull(self.se.bill_to_gstin, "") != self.se.bill_from_gstin)
            .where(self.se.purpose == "Send to Subcontractor")
        )

        if self.filters.company_gstin:
            query = query.where(self.se.bill_from_gstin == self.filters.company_gstin)

        return query

    def get_query_table_4_sr(self):
        """
        Construct the query for Table-4 Subcontracting Receipt.
        - Table-4 is for goods sent to job worker.
        - This query is for Subcontracting Receipt Returns.
        """
        query = (
            self.get_base_query_table_4(self.sr, self.sr_item)
            .select(
                self.sr_item.stock_uom.as_("uom"),
                self.sr.company_gstin,
                self.sr.supplier_gstin,
                self.sr_doctype.as_("invoice_type"),
            )
            .where(IfNull(self.sr.supplier_gstin, "") != self.sr.company_gstin)
            .where(self.sr.is_return == 1)
        )

        if self.filters.company_gstin:
            query = query.where(self.sr.company_gstin == self.filters.company_gstin)

        return query

    def get_base_query_table_5A(self, doc, doc_item, ref_doc):
        """Construct the base query for Table-5A."""
        query = (
            frappe.qb.from_(doc)
            .inner_join(doc_item)
            .on(doc.name == doc_item.parent)
            .inner_join(ref_doc)
            .on(ref_doc.parent == doc.name)
            .select(
                IfNull(doc_item.item_code, doc_item.item_name).as_("item_code"),
                doc_item.qty,
                doc_item.gst_hsn_code,
                IfNull(doc.supplier, "").as_("supplier"),
                IfNull(doc.name, "").as_("invoice_no"),
                doc.posting_date,
                doc.is_return,
                IfNull(doc.place_of_supply, "").as_("place_of_supply"),
                doc.base_grand_total.as_("invoice_total"),
                IfNull(doc_item.gst_treatment, "Not Defined").as_("gst_treatment"),
                ref_doc.link_doctype.as_("original_challan_invoice_type"),
                IfNull(ref_doc.link_name, "").as_("original_challan_no"),
            )
            .where(doc.docstatus == 1)
            .orderby(doc.name, order=Order.desc)
        )

        query = self.get_query_with_common_filters(query, doc)

        return query

    def get_query_table_5A_se(self):
        """
        Construct the query for Table-5A Stock Entry.
        - Table-5A is for goods received from job worker.
        - This query is for Stock Entry Returns.
        """
        query = (
            self.get_base_query_table_5A(self.se, self.se_item, self.ref_doc)
            .select(
                self.se_item.uom,
                self.se.bill_to_gstin.as_("supplier_gstin"),
                self.se.bill_from_gstin.as_("company_gstin"),
                self.se_doctype.as_("invoice_type"),
            )
            .where(IfNull(self.se.bill_to_gstin, "") != self.se.bill_from_gstin)
            .where(self.se.is_return == 1)
            .where(self.se.purpose == "Material Transfer")
        )

        if self.filters.company_gstin:
            query = query.where(self.se.bill_from_gstin == self.filters.company_gstin)

        return query

    def get_query_table_5A_sr(self):
        """
        Construct the query for Table-5A Subcontracting Receipt.
        - Table-5A is for goods received from job worker.
        - This query is for Subcontracting Receipt.
        """
        query = (
            self.get_base_query_table_5A(self.sr, self.sr_item, self.ref_doc)
            .select(
                self.sr_item.stock_uom.as_("uom"),
                self.sr.company_gstin,
                self.sr.supplier_gstin,
                self.sr_doctype.as_("invoice_type"),
            )
            .where(IfNull(self.sr.supplier_gstin, "") != self.sr.company_gstin)
            .where(self.sr.is_return == 0)
        )

        if self.filters.company_gstin:
            query = query.where(self.sr.company_gstin == self.filters.company_gstin)

        return query

    def get_query_with_common_filters(self, query, doc):
        """Apply common filters to the query."""
        if self.filters.company:
            query = query.where(doc.company == self.filters.company)

        if self.filters.from_date:
            query = query.where(
                Date(doc.posting_date) >= getdate(self.filters.from_date)
            )

        if self.filters.to_date:
            query = query.where(Date(doc.posting_date) <= getdate(self.filters.to_date))

        return query
