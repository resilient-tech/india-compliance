# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt
import re
from itertools import combinations

from pypika import Order

import frappe
from frappe.query_builder import Case, Criterion
from frappe.query_builder.functions import Date, IfNull, Sum
from frappe.utils import cint, flt, getdate

from india_compliance.gst_india.constants import GST_REFUND_TAX_TYPES
from india_compliance.gst_india.utils import (
    get_escaped_name,
    get_full_gst_uom,
    validate_invoice_number,
)
from india_compliance.gst_india.utils.gstr_1 import (
    CATEGORY_SUB_CATEGORY_MAPPING,
    HSN_BIFURCATION_FROM,
    GSTR1_B2B_InvoiceType,
    GSTR1_Category,
    GSTR1_SubCategory,
    get_b2c_limit,
)

CATEGORY_CONDITIONS = {
    GSTR1_Category.B2B.value: {
        "category": "is_b2b_invoice",
        "sub_category": "set_for_b2b",
    },
    GSTR1_Category.B2CL.value: {
        "category": "is_b2cl_invoice",
        "sub_category": "set_for_b2cl",
    },
    GSTR1_Category.EXP.value: {
        "category": "is_export_invoice",
        "sub_category": "set_for_exports",
    },
    GSTR1_Category.B2CS.value: {
        "category": "is_b2cs_invoice",
        "sub_category": "set_for_b2cs",
    },
    GSTR1_Category.NIL_EXEMPT.value: {
        "category": "is_nil_rated_exempted_non_gst_invoice",
        "sub_category": "set_for_nil_exp_non_gst",
    },
    GSTR1_Category.CDNR.value: {
        "category": "is_cdnr_invoice",
        "sub_category": "set_for_cdnr",
    },
    GSTR1_Category.CDNUR.value: {
        "category": "is_cdnur_invoice",
        "sub_category": "set_for_cdnur",
    },
    GSTR1_Category.SUPECOM.value: {
        "category": "is_ecommerce_sales_invoice",
        "sub_category": "set_for_ecommerce_supply_type",
    },
}


class GSTR1Query:
    def __init__(
        self, filters=None, additional_si_columns=None, additional_si_item_columns=None
    ):
        self.si = frappe.qb.DocType("Sales Invoice")
        self.si_item = frappe.qb.DocType("Sales Invoice Item")
        self.si_taxes = frappe.qb.DocType("Sales Taxes and Charges")
        self.filters = frappe._dict(filters or {})
        self.additional_si_columns = additional_si_columns or []
        self.additional_si_item_columns = additional_si_item_columns or []

    def get_base_query(self):
        self.taxes_query = self.get_taxes_query()  # subquery for refund amount taxes
        returned_si = frappe.qb.DocType("Sales Invoice", alias="returned_si")

        query = (
            frappe.qb.from_(self.si)
            .inner_join(self.si_item)
            .on(self.si.name == self.si_item.parent)
            .left_join(returned_si)
            .on(self.si.return_against == returned_si.name)
            .left_join(self.taxes_query)
            .on(self.si.name == self.taxes_query.parent)
            .select(
                IfNull(self.si_item.item_code, self.si_item.item_name).as_("item_code"),
                self.si_item.qty,
                self.si_item.gst_hsn_code,
                self.si_item.uom,
                self.si.billing_address_gstin,
                self.si.company_gstin,
                self.si.customer_name,
                self.si.name.as_("invoice_no"),
                self.si.posting_date,
                IfNull(self.si.place_of_supply, "").as_("place_of_supply"),
                self.si.is_reverse_charge,
                IfNull(self.si.ecommerce_gstin, "").as_("ecommerce_gstin"),
                self.si.is_return,
                self.si.is_debit_note,
                self.si.return_against,
                self.si.is_export_with_gst,
                self.si.port_code.as_("shipping_port_code"),
                self.si.shipping_bill_number,
                self.si.shipping_bill_date,
                self.si.gst_category,
                IfNull(self.si_item.gst_treatment, "Not Defined").as_("gst_treatment"),
                (
                    self.si_item.cgst_rate
                    + self.si_item.sgst_rate
                    + self.si_item.igst_rate
                ).as_("gst_rate"),
                self.si_item.taxable_value,
                self.si_item.cgst_amount,
                self.si_item.sgst_amount,
                self.si_item.igst_amount,
                self.si_item.cess_amount,
                self.si_item.cess_non_advol_amount,
                (self.si_item.cess_amount + self.si_item.cess_non_advol_amount).as_(
                    "total_cess_amount"
                ),
                (
                    self.si_item.cgst_amount
                    + self.si_item.sgst_amount
                    + self.si_item.igst_amount
                    + self.si_item.cess_amount
                    + self.si_item.cess_non_advol_amount
                ).as_("total_tax"),
                (
                    self.si_item.taxable_value
                    + self.si_item.cgst_amount
                    + self.si_item.sgst_amount
                    + self.si_item.igst_amount
                    + self.si_item.cess_amount
                    + self.si_item.cess_non_advol_amount
                ).as_("total_amount"),
            )
            .where(self.si.docstatus == 1)
            .where(self.si.is_opening != "Yes")
            .where(IfNull(self.si.billing_address_gstin, "") != self.si.company_gstin)
            .orderby(
                self.si.posting_date,
                self.si.name,
                self.si_item.item_code,
                order=Order.desc,
            )
        )

        query = self.select_totals(query, self.si, "invoice_total")
        query = self.select_totals(query, returned_si, "returned_invoice_total")

        if self.additional_si_columns:
            for col in self.additional_si_columns:
                query = query.select(self.si[col])

        if self.additional_si_item_columns:
            for col in self.additional_si_item_columns:
                query = query.select(self.si_item[col])

        query = self.get_query_with_common_filters(query)

        return query

    def get_query_with_common_filters(self, query):
        if self.filters.company:
            query = query.where(self.si.company == self.filters.company)

        if self.filters.company_gstin:
            query = query.where(self.si.company_gstin == self.filters.company_gstin)

        if self.filters.from_date:
            query = query.where(
                Date(self.si.posting_date) >= getdate(self.filters.from_date)
            )

        if self.filters.to_date:
            query = query.where(
                Date(self.si.posting_date) <= getdate(self.filters.to_date)
            )

        return query

    def get_taxes_query(self):
        return (
            frappe.qb.from_(self.si_taxes)
            .select(
                Sum(self.si_taxes.base_tax_amount_after_discount_amount).as_(
                    "refund_amount"
                ),
                self.si_taxes.parent,
            )
            .where(self.si_taxes.gst_tax_type.isin(GST_REFUND_TAX_TYPES))
            .groupby(self.si_taxes.parent)
        )

    def select_totals(self, query, si_doc, key):
        # TODO: Handle TDS
        return query.select(
            (
                IfNull(
                    Case()
                    .when(
                        si_doc.base_rounded_total != 0,
                        si_doc.base_rounded_total,
                    )
                    .else_(si_doc.base_grand_total),
                    0,
                )
                - IfNull(self.taxes_query.refund_amount, 0)
            ).as_(key)
        )


def cache_invoice_condition(func):
    def wrapped(self, invoice):
        if (cond := self.invoice_conditions.get(func.__name__)) is not None:
            return cond

        cond = func(self, invoice)
        self.invoice_conditions[func.__name__] = cond
        return cond

    return wrapped


class GSTR1Conditions:
    @cache_invoice_condition
    def is_nil_rated(self, invoice):
        return invoice.gst_treatment == "Nil-Rated"

    @cache_invoice_condition
    def is_exempted(self, invoice):
        return invoice.gst_treatment == "Exempted"

    @cache_invoice_condition
    def is_non_gst(self, invoice):
        return invoice.gst_treatment == "Non-GST"

    @cache_invoice_condition
    def is_nil_rated_exempted_or_non_gst(self, invoice):
        return not self.is_export(invoice) and (
            self.is_nil_rated(invoice)
            or self.is_exempted(invoice)
            or self.is_non_gst(invoice)
        )

    @cache_invoice_condition
    def is_cn_dn(self, invoice):
        return invoice.is_return or invoice.is_debit_note

    @cache_invoice_condition
    def has_gstin_and_is_not_export(self, invoice):
        return invoice.billing_address_gstin and not self.is_export(invoice)

    @cache_invoice_condition
    def is_export(self, invoice):
        return (
            invoice.place_of_supply == "96-Other Countries"
            and invoice.gst_category == "Overseas"
        )

    @cache_invoice_condition
    def is_inter_state(self, invoice):
        # if pos is not avaialble default to False
        if not invoice.place_of_supply:
            return False

        return invoice.company_gstin[:2] != invoice.place_of_supply[:2]

    @cache_invoice_condition
    def is_b2cl_cn_dn(self, invoice):
        invoice_total = (
            max(abs(invoice.invoice_total), abs(invoice.returned_invoice_total))
            if invoice.return_against
            else invoice.invoice_total
        )

        return (
            abs(invoice_total) > get_b2c_limit(invoice.posting_date)
        ) and self.is_inter_state(invoice)

    @cache_invoice_condition
    def is_b2cl_inv(self, invoice):
        return abs(invoice.invoice_total) > get_b2c_limit(
            invoice.posting_date
        ) and self.is_inter_state(invoice)


class GSTR1CategoryConditions(GSTR1Conditions):
    def is_nil_rated_exempted_non_gst_invoice(self, invoice):
        return (
            self.is_nil_rated(invoice)
            or self.is_exempted(invoice)
            or self.is_non_gst(invoice)
        )

    def is_b2b_invoice(self, invoice):
        return (
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and not self.is_cn_dn(invoice)
            and self.has_gstin_and_is_not_export(invoice)
        )

    def is_export_invoice(self, invoice):
        return (
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and not self.is_cn_dn(invoice)
            and self.is_export(invoice)
        )

    def is_b2cl_invoice(self, invoice):
        return (
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and not self.is_cn_dn(invoice)
            and not self.has_gstin_and_is_not_export(invoice)
            and not self.is_export(invoice)
            and self.is_b2cl_inv(invoice)
        )

    def is_b2cs_invoice(self, invoice):
        return (
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and not self.has_gstin_and_is_not_export(invoice)
            and not self.is_export(invoice)
            and (not self.is_b2cl_cn_dn(invoice) or not self.is_b2cl_inv(invoice))
        )

    def is_cdnr_invoice(self, invoice):
        return (
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and self.is_cn_dn(invoice)
            and self.has_gstin_and_is_not_export(invoice)
        )

    def is_cdnur_invoice(self, invoice):
        return (
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and self.is_cn_dn(invoice)
            and not self.has_gstin_and_is_not_export(invoice)
            and (self.is_export(invoice) or self.is_b2cl_cn_dn(invoice))
        )

    def is_ecommerce_sales_invoice(self, invoice):
        return bool(invoice.ecommerce_gstin)


class GSTR1Subcategory(GSTR1CategoryConditions):
    def set_for_b2b(self, invoice):
        self._set_invoice_type_for_b2b_and_cdnr(invoice)

    def set_for_b2cl(self, invoice):
        # NO INVOICE VALUE
        invoice.invoice_sub_category = GSTR1_SubCategory.B2CL.value

    def set_for_exports(self, invoice):
        if invoice.is_export_with_gst:
            invoice.invoice_sub_category = GSTR1_SubCategory.EXPWP.value
            invoice.invoice_type = "WPAY"

        else:
            invoice.invoice_sub_category = GSTR1_SubCategory.EXPWOP.value
            invoice.invoice_type = "WOPAY"

    def set_for_b2cs(self, invoice):
        # NO INVOICE VALUE
        invoice.invoice_sub_category = GSTR1_SubCategory.B2CS.value

    def set_for_nil_exp_non_gst(self, invoice):
        # INVOICE TYPE
        is_registered = self.has_gstin_and_is_not_export(invoice)
        is_interstate = self.is_inter_state(invoice)

        gst_registration = "registered" if is_registered else "unregistered"
        supply_type = "Inter-State" if is_interstate else "Intra-State"

        invoice.invoice_type = f"{supply_type} supplies to {gst_registration} persons"
        invoice.invoice_sub_category = GSTR1_SubCategory.NIL_EXEMPT.value

    def set_for_cdnr(self, invoice):
        self._set_invoice_type_for_b2b_and_cdnr(invoice)
        invoice.invoice_sub_category = GSTR1_SubCategory.CDNR.value

    def set_for_cdnur(self, invoice):
        invoice.invoice_sub_category = GSTR1_SubCategory.CDNUR.value
        if self.is_export(invoice):
            if invoice.is_export_with_gst:
                invoice.invoice_type = "EXPWP"
                return

            invoice.invoice_type = "EXPWOP"
            return

        invoice.invoice_type = "B2CL"
        return

    def set_for_ecommerce_supply_type(self, invoice):
        if invoice.is_reverse_charge:
            invoice.ecommerce_supply_type = GSTR1_SubCategory.SUPECOM_9_5.value
            return

        invoice.ecommerce_supply_type = GSTR1_SubCategory.SUPECOM_52.value

    def _set_invoice_type_for_b2b_and_cdnr(self, invoice):
        if invoice.gst_category == "Deemed Export":
            invoice.invoice_type = GSTR1_B2B_InvoiceType.DE.value
            invoice.invoice_sub_category = GSTR1_SubCategory.DE.value

        elif invoice.gst_category == "SEZ":
            if invoice.is_export_with_gst:
                invoice.invoice_type = GSTR1_B2B_InvoiceType.SEWP.value
                invoice.invoice_sub_category = GSTR1_SubCategory.SEZWP.value

            else:
                invoice.invoice_type = GSTR1_B2B_InvoiceType.SEWOP.value
                invoice.invoice_sub_category = GSTR1_SubCategory.SEZWOP.value

        elif invoice.is_reverse_charge:
            invoice.invoice_type = GSTR1_B2B_InvoiceType.R.value
            invoice.invoice_sub_category = GSTR1_SubCategory.B2B_REVERSE_CHARGE.value

        else:
            invoice.invoice_type = GSTR1_B2B_InvoiceType.R.value
            invoice.invoice_sub_category = GSTR1_SubCategory.B2B_REGULAR.value

    def set_hsn_sub_category(self, invoice, bifurcate_hsn):
        if not bifurcate_hsn:
            invoice.hsn_sub_category = GSTR1_SubCategory.HSN.value

        elif invoice.gst_category in ("Unregistered", "Overseas"):
            invoice.hsn_sub_category = GSTR1_SubCategory.HSN_B2C.value

        else:
            invoice.hsn_sub_category = GSTR1_SubCategory.HSN_B2B.value


class GSTR1Invoices(GSTR1Query, GSTR1Subcategory):
    AMOUNT_FIELDS = {
        "taxable_value": 0,
        "igst_amount": 0,
        "cgst_amount": 0,
        "sgst_amount": 0,
        "total_cess_amount": 0,
    }

    def process_invoices(self, invoices, bifurcate_hsn=None):
        settings = frappe.get_cached_doc("GST Settings")
        identified_uom = {}

        if bifurcate_hsn is None:
            bifurcate_hsn = self.is_hsn_bifurcation_needed()

        for invoice in invoices:
            self.invoice_conditions = {}
            self.assign_categories(invoice)
            self.set_hsn_sub_category(invoice, bifurcate_hsn)

            if invoice.gst_hsn_code and invoice.gst_hsn_code.startswith("99"):
                invoice["uom"] = "OTH-OTHERS"
                invoice["qty"] = 0
                continue

            uom = invoice.get("uom", "")
            if uom in identified_uom:
                invoice["uom"] = identified_uom[uom]
            else:
                gst_uom = get_full_gst_uom(uom, settings)
                identified_uom[uom] = gst_uom
                invoice["uom"] = gst_uom

    def assign_categories(self, invoice):
        if not invoice.invoice_sub_category:
            self.set_invoice_category(invoice)
            self.set_invoice_sub_category_and_type(invoice)

        if invoice.ecommerce_gstin and not invoice.ecommerce_supply_type:
            self.set_for_ecommerce_supply_type(invoice)

    def set_invoice_category(self, invoice):
        for category, functions in CATEGORY_CONDITIONS.items():
            if getattr(self, functions["category"], None)(invoice):
                invoice.invoice_category = category
                return

    def set_invoice_sub_category_and_type(self, invoice):
        category = invoice.invoice_category
        function = CATEGORY_CONDITIONS[category]["sub_category"]
        getattr(self, function, None)(invoice)

    def get_invoices_for_item_wise_summary(self):
        query = self.get_base_query()

        return query.run(as_dict=True)

    def get_invoices_for_hsn_wise_summary(self):
        query = self.get_base_query()

        query = (
            frappe.qb.from_(query)
            .select(
                "*",
                Sum(query.qty).as_("qty"),
                Sum(query.taxable_value).as_("taxable_value"),
                Sum(query.cgst_amount).as_("cgst_amount"),
                Sum(query.sgst_amount).as_("sgst_amount"),
                Sum(query.igst_amount).as_("igst_amount"),
                Sum(query.total_cess_amount).as_("total_cess_amount"),
                Sum(query.total_tax).as_("total_tax"),
                Sum(query.total_amount).as_("total_amount"),
            )
            .groupby(
                query.invoice_no,
                query.gst_hsn_code,
                query.gst_rate,
                query.gst_treatment,
                query.uom,
            )
            .orderby(
                query.posting_date, query.invoice_no, query.item_code, order=Order.desc
            )
        )

        return query.run(as_dict=True)

    def get_filtered_invoices(
        self, invoices, invoice_category=None, invoice_sub_category=None
    ):
        filtered_invoices = []
        functions = CATEGORY_CONDITIONS.get(invoice_category)
        condition = getattr(self, functions["category"], None)

        for invoice in invoices:
            self.invoice_conditions = {}
            if not condition(invoice):
                continue

            invoice.invoice_category = invoice_category
            self.set_invoice_sub_category_and_type(invoice)

            if not invoice_sub_category:
                filtered_invoices.append(invoice)

            elif invoice_sub_category == invoice.invoice_sub_category:
                filtered_invoices.append(invoice)

            elif invoice_sub_category == invoice.ecommerce_supply_type:
                filtered_invoices.append(invoice)

        self.process_invoices(invoices)

        return filtered_invoices

    def get_overview(self):
        final_summary = []
        sub_category_summary = self.get_sub_category_summary()

        IGNORED_CATEGORIES = {
            GSTR1_Category.AT,
            GSTR1_Category.TXP,
            GSTR1_Category.DOC_ISSUE,
            GSTR1_Category.HSN,
        }

        is_ecommerce_sales_enabled = frappe.get_cached_value(
            "GST Settings", None, "enable_sales_through_ecommerce_operators"
        )
        if not is_ecommerce_sales_enabled:
            IGNORED_CATEGORIES.add(GSTR1_Category.SUPECOM)

        for category, sub_categories in CATEGORY_SUB_CATEGORY_MAPPING.items():
            if category in IGNORED_CATEGORIES:
                continue

            category_summary = {
                "description": category.value,
                "no_of_records": 0,
                "indent": 0,
                **self.AMOUNT_FIELDS,
            }
            final_summary.append(category_summary)

            for sub_category in sub_categories:
                sub_category_row = sub_category_summary[sub_category.value]
                category_summary["no_of_records"] += sub_category_row["no_of_records"]

                for key in self.AMOUNT_FIELDS:
                    category_summary[key] += sub_category_row[key]

                final_summary.append(sub_category_row)

        self.update_overlaping_invoice_summary(sub_category_summary, final_summary)

        return final_summary

    def get_sub_category_summary(self):
        invoices = self.get_invoices_for_item_wise_summary()
        self.process_invoices(invoices)

        summary = {}

        for category in GSTR1_SubCategory:
            category = category.value
            summary[category] = {
                "description": category,
                "no_of_records": 0,
                "indent": 1,
                "unique_records": set(),
                **self.AMOUNT_FIELDS,
            }

        def _update_summary_row(row, sub_category_field="invoice_sub_category"):
            summary_row = summary[row.get(sub_category_field, row["invoice_category"])]

            for key in self.AMOUNT_FIELDS:
                summary_row[key] += row[key]

            summary_row["unique_records"].add(row.invoice_no)

        for row in invoices:
            _update_summary_row(row)

            if row.ecommerce_gstin:
                _update_summary_row(row, "ecommerce_supply_type")

        for summary_row in summary.values():
            summary_row["no_of_records"] = len(summary_row["unique_records"])

        return summary

    def update_overlaping_invoice_summary(self, sub_category_summary, final_summary):
        nil_exempt = GSTR1_SubCategory.NIL_EXEMPT.value
        supecom_52 = GSTR1_SubCategory.SUPECOM_52.value
        supecom_9_5 = GSTR1_SubCategory.SUPECOM_9_5.value

        # Get Unique Taxable Invoices
        unique_invoices = set()
        for category, row in sub_category_summary.items():
            if category in (nil_exempt, supecom_52, supecom_9_5):
                continue

            unique_invoices.update(row["unique_records"])

        # Get Overlaping Invoices
        invoice_sets = [
            sub_category_summary[nil_exempt]["unique_records"],
            {
                *sub_category_summary[supecom_52]["unique_records"],
                *sub_category_summary[supecom_9_5]["unique_records"],
            },
            unique_invoices,
        ]

        overlaping_invoices = []

        for set1, set2 in combinations(invoice_sets, 2):
            overlaping_invoices.extend(set1.intersection(set2))

        # Update Summary
        if overlaping_invoices:
            final_summary.append(
                {
                    "description": "Overlaping Invoices in Nil-Rated/Exempt/Non-GST and E-commerce Sales",
                    "no_of_records": -len(overlaping_invoices),
                }
            )

    def is_hsn_bifurcation_needed(self):
        # From GSTR-1
        if self.filters.get("month_or_quarter"):
            from_date = getdate(
                f"01-{self.filters.month_or_quarter}-{self.filters.year}"
            )
        else:
            from_date = getdate(self.filters.from_date)

        return from_date >= HSN_BIFURCATION_FROM


class GSTR1DocumentIssuedSummary:
    def __init__(self, filters):
        self.filters = filters
        self.sales_invoice = frappe.qb.DocType("Sales Invoice")
        self.sales_invoice_item = frappe.qb.DocType("Sales Invoice Item")
        self.purchase_invoice = frappe.qb.DocType("Purchase Invoice")
        self.stock_entry = frappe.qb.DocType("Stock Entry")
        self.subcontracting_receipt = frappe.qb.DocType("Subcontracting Receipt")
        self.queries = {
            "Sales Invoice": self.get_query_for_sales_invoice,
            "Purchase Invoice": self.get_query_for_purchase_invoice,
            "Stock Entry": self.get_query_for_stock_entry,
            "Subcontracting Receipt": self.get_query_for_subcontracting_receipt,
        }

    def get_data(self) -> list:
        return self.get_document_summary()

    def get_document_summary(self):
        summarized_data = []

        for doctype, query in self.queries.items():
            data = query().run(as_dict=True)
            data = self.handle_amended_docs(data)
            for (
                nature_of_document,
                seperated_data,
            ) in self.seperate_data_by_nature_of_document(data, doctype).items():
                summarized_data.extend(
                    self.seperate_data_by_naming_series(
                        seperated_data, nature_of_document
                    )
                )

        return summarized_data

    def build_query(
        self,
        doctype,
        party_gstin_field,
        company_gstin_field="company_gstin",
        address_field=None,
        additional_selects=None,
        additional_conditions=None,
    ):
        party_gstin_field = getattr(doctype, party_gstin_field, None)
        company_gstin_field = getattr(doctype, company_gstin_field, None)
        address_field = getattr(doctype, address_field, None)

        query = (
            frappe.qb.from_(doctype)
            .select(
                doctype.name,
                IfNull(doctype.naming_series, "").as_("naming_series"),
                doctype.creation,
                doctype.docstatus,
                doctype.amended_from,
                Case()
                .when(
                    IfNull(party_gstin_field, "") == company_gstin_field,
                    1,
                )
                .else_(0)
                .as_("same_gstin_billing"),
            )
            .where(doctype.company == self.filters.company)
            .where(
                doctype.posting_date.between(
                    self.filters.from_date, self.filters.to_date
                )
            )
            .orderby(doctype.name)
            .groupby(doctype.name)
        )

        if additional_selects:
            query = query.select(*additional_selects)

        if additional_conditions:
            query = query.where(Criterion.all(additional_conditions))

        if self.filters.company_address:
            query = query.where(address_field == self.filters.company_address)

        if self.filters.company_gstin:
            query = query.where(company_gstin_field == self.filters.company_gstin)

        return query

    def get_query_for_sales_invoice(self):
        additional_selects = [
            self.sales_invoice.is_return,
            self.sales_invoice.is_debit_note,
            self.sales_invoice.is_opening,
        ]

        query = self.build_query(
            doctype=self.sales_invoice,
            party_gstin_field="billing_address_gstin",
            address_field="company_address",
            additional_selects=additional_selects,
        )

        return (
            query.join(self.sales_invoice_item)
            .on(self.sales_invoice.name == self.sales_invoice_item.parent)
            .select(
                self.sales_invoice_item.gst_treatment,
            )
        )

    def get_query_for_purchase_invoice(self):
        additional_selects = [
            self.purchase_invoice.is_opening,
        ]

        additional_conditions = [
            self.purchase_invoice.is_reverse_charge == 1,
            IfNull(self.purchase_invoice.supplier_gstin, "") == "",
        ]
        return self.build_query(
            doctype=self.purchase_invoice,
            party_gstin_field="supplier_gstin",
            address_field="billing_address",
            additional_selects=additional_selects,
            additional_conditions=additional_conditions,
        )

    def get_query_for_stock_entry(self):
        additional_selects = [
            self.stock_entry.is_opening,
        ]

        additional_conditions = [
            self.stock_entry.purpose == "Send to Subcontractor",
            self.stock_entry.subcontracting_order != "",
        ]
        return self.build_query(
            doctype=self.stock_entry,
            party_gstin_field="bill_to_gstin",
            company_gstin_field="bill_from_gstin",
            address_field="bill_from_address",
            additional_selects=additional_selects,
            additional_conditions=additional_conditions,
        )

    def get_query_for_subcontracting_receipt(self):
        additional_conditions = [
            self.subcontracting_receipt.is_return == 1,
        ]
        return self.build_query(
            doctype=self.subcontracting_receipt,
            party_gstin_field="supplier_gstin",
            address_field="billing_address",
            additional_conditions=additional_conditions,
        )

    def seperate_data_by_naming_series(self, data, nature_of_document):
        if not data:
            return []

        slice_indices = []
        summarized_data = []

        for i in range(1, len(data)):
            if self.is_same_naming_series(data[i - 1].name, data[i].name):
                continue
            slice_indices.append(i)

        document_series_list = [
            data[i:j] for i, j in zip([0] + slice_indices, slice_indices + [None])
        ]

        for series in document_series_list:
            draft_count = sum(1 for doc in series if doc.docstatus == 0)
            total_submitted_count = sum(1 for doc in series if doc.docstatus == 1)
            cancelled_count = sum(1 for doc in series if doc.docstatus == 2)

            summarized_data.append(
                {
                    "naming_series": series[0].naming_series.replace(".", ""),
                    "nature_of_document": nature_of_document,
                    "from_serial_no": series[0].name,
                    "to_serial_no": series[-1].name,
                    "total_submitted": total_submitted_count,
                    "cancelled": cancelled_count,
                    "total_draft": draft_count,
                    "total_issued": draft_count
                    + total_submitted_count
                    + cancelled_count,
                }
            )

        return summarized_data

    def is_same_naming_series(self, name_1, name_2):
        """
        Checks if two document names belong to the same naming series.

        Args:
            name_1 (str): The first document name.
            name_2 (str): The second document name.

        Returns:
            bool: True if the two document names belong to the same naming series, False otherwise.

        Limitations:
            Case 1: When the difference between the serial numbers in the document names is a
                    multiple of 10. For example, 'SINV-00010-2023' and 'SINV-00020-2023'.
            Case 2: When the serial numbers are identical, but the months differ.
                    For example, 'SINV-01-2023-001' and 'SINV-02-2023-001'.

            Above cases are false positives and will be considered as same naming series
            although they are not.
        """

        alphabet_pattern = re.compile(r"[A-Za-z]+")
        number_pattern = re.compile(r"\d+")

        a_0 = "".join(alphabet_pattern.findall(name_1))
        n_0 = "".join(number_pattern.findall(name_1))

        a_1 = "".join(alphabet_pattern.findall(name_2))
        n_1 = "".join(number_pattern.findall(name_2))

        if a_1 != a_0:
            return False

        if len(n_0) != len(n_1):
            return False

        # If common suffix is present between the two names, remove it to compare the numbers
        # Example: SINV-00001-2023 and SINV-00002-2023, the common suffix 2023 will be removed

        suffix_length = 0

        for i in range(len(n_0) - 1, 0, -1):
            if n_0[i] == n_1[i]:
                suffix_length += 1
            else:
                break

        if suffix_length:
            n_0, n_1 = n_0[:-suffix_length], n_1[:-suffix_length]

        return cint(n_1) - cint(n_0) == 1

    def seperate_data_by_nature_of_document(self, data, doctype):
        nature_of_document = {
            "Excluded from Report (Invalid Invoice Number)": [],
            "Excluded from Report (Same GSTIN Billing)": [],
            "Excluded from Report (Is Opening Entry)": [],
            "Invoices for outward supply": [],
            "Debit Note": [],
            "Credit Note": [],
            "Invoices for inward supply from unregistered person": [],
            "Delivery Challan for job work": [],
        }

        for doc in data:
            if not validate_invoice_number(doc, throw=False):
                nature_of_document[
                    "Excluded from Report (Invalid Invoice Number)"
                ].append(doc)

            elif doc.is_opening == "Yes":
                nature_of_document["Excluded from Report (Is Opening Entry)"].append(
                    doc
                )
            elif doc.same_gstin_billing:
                nature_of_document["Excluded from Report (Same GSTIN Billing)"].append(
                    doc
                )
            elif doctype == "Purchase Invoice":
                nature_of_document[
                    "Invoices for inward supply from unregistered person"
                ].append(doc)
            elif doctype == "Stock Entry" or doctype == "Subcontracting Receipt":
                nature_of_document["Delivery Challan for job work"].append(doc)
            # for Sales Invoice
            elif doc.is_return:
                nature_of_document["Credit Note"].append(doc)
            elif doc.is_debit_note:
                nature_of_document["Debit Note"].append(doc)
            else:
                nature_of_document["Invoices for outward supply"].append(doc)

        return nature_of_document

    def handle_amended_docs(self, data):
        """Move amended docs like SINV-00001-1 to the end of the list"""

        data_dict = {doc.name: doc for doc in data}
        amended_dict = {}

        for doc in data:
            if (
                doc.amended_from
                and len(doc.amended_from) != len(doc.name)
                or doc.amended_from in amended_dict
            ):
                amended_dict[doc.name] = doc
                data_dict.pop(doc.name)

        data_dict.update(amended_dict)

        return list(data_dict.values())


class GSTR11A11BData:
    def __init__(self, filters, gst_accounts):
        self.filters = filters

        self.pe = frappe.qb.DocType("Payment Entry")
        self.pe_ref = frappe.qb.DocType("Payment Entry Reference")
        self.gl_entry = frappe.qb.DocType("GL Entry")
        self.gst_accounts = gst_accounts

    def get_data(self):
        if self.filters.get("type_of_business") == "Advances":
            records = self.get_11A_query().run(as_dict=True)
        elif self.filters.get("type_of_business") == "Adjustment":
            records = self.get_11B_query().run(as_dict=True)

        return self.process_data(records)

    def get_11A_query(self):
        return (
            self.get_query("Advances")
            .select(self.pe.paid_amount.as_("taxable_value"))
            .groupby(self.pe.name)
        )

    def get_11B_query(self):
        return (
            self.get_query("Adjustment")
            .join(self.pe_ref)
            .on(self.pe_ref.name == self.gl_entry.voucher_detail_no)
            .select(self.pe_ref.allocated_amount.as_("taxable_value"))
            .groupby(self.gl_entry.voucher_detail_no)
        )

    def get_query(self, type_of_business):
        cr_or_dr = "credit" if type_of_business == "Advances" else "debit"
        cr_or_dr_amount_field = getattr(
            self.gl_entry, f"{cr_or_dr}_in_account_currency"
        )
        cess_account = get_escaped_name(self.gst_accounts.cess_account)

        return (
            frappe.qb.from_(self.gl_entry)
            .join(self.pe)
            .on(self.pe.name == self.gl_entry.voucher_no)
            .select(
                self.pe.place_of_supply,
                Sum(
                    Case()
                    .when(
                        self.gl_entry.account != IfNull(cess_account, ""),
                        cr_or_dr_amount_field,
                    )
                    .else_(0)
                ).as_("tax_amount"),
                Sum(
                    Case()
                    .when(
                        self.gl_entry.account == IfNull(cess_account, ""),
                        cr_or_dr_amount_field,
                    )
                    .else_(0)
                ).as_("cess_amount"),
            )
            .where(Criterion.all(self.get_conditions()))
            .where(cr_or_dr_amount_field > 0)
        )

    def get_conditions(self):
        gst_accounts_list = [
            account_head for account_head in self.gst_accounts.values() if account_head
        ]

        conditions = []

        conditions.append(self.gl_entry.is_cancelled == 0)
        conditions.append(self.gl_entry.voucher_type == "Payment Entry")
        conditions.append(self.gl_entry.company == self.filters.get("company"))
        conditions.append(self.gl_entry.account.isin(gst_accounts_list))
        conditions.append(
            self.gl_entry.posting_date[
                self.filters.get("from_date") : self.filters.get("to_date")
            ]
        )

        if self.filters.get("company_gstin"):
            conditions.append(
                self.gl_entry.company_gstin == self.filters.get("company_gstin")
            )

        return conditions

    def process_data(self, records):
        data = {}
        for entry in records:
            taxable_value = flt(entry.taxable_value, 2)
            tax_rate = (
                round(((entry.tax_amount / taxable_value) * 100))
                if taxable_value
                else 0
            )

            data.setdefault((entry.place_of_supply, tax_rate), [0.0, 0.0])

            data[(entry.place_of_supply, tax_rate)][0] += taxable_value
            data[(entry.place_of_supply, tax_rate)][1] += flt(entry.cess_amount, 2)

        return data
