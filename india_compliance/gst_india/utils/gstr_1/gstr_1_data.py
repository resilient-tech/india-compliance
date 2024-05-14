# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

from enum import Enum

from pypika import Order

import frappe
from frappe.query_builder.functions import Date, IfNull, Sum
from frappe.utils import getdate

from india_compliance.gst_india.utils import get_full_gst_uom

B2C_LIMIT = 2_50_000

# TODO: Enum for Invoice Type


class GSTR1_Categories(Enum):
    """
    Overview Page of GSTR-1
    """

    # Invoice Items Bifurcation
    B2B = "B2B, SEZ, DE"
    B2CL = "B2C (Large)"
    EXP = "Exports"
    B2CS = "B2C (Others)"
    NIL_EXEMPT = "Nil-Rated, Exempted, Non-GST"
    CDNR = "Credit/Debit Notes (Registered)"
    CDNUR = "Credit/Debit Notes (Unregistered)"
    # Other Categories
    AT = "Advances Received"
    TXP = "Advances Adjusted"
    DOC_ISSUE = "Document Issued"
    HSN = "HSN Summary"


class GSTR1_SubCategories(Enum):
    """
    Summary Page of GSTR-1
    """

    # Invoice Items Bifurcation
    B2B_REGULAR = "B2B Regular"  # Regular B2B
    B2B_REVERSE_CHARGE = "B2B Reverse Charge"  # Regular B2B
    SEZWP = "SEZWP"  # SEZ supplies with payment
    SEZWOP = "SEZWOP"  # SEZ supplies without payment
    DE = "Deemed Exports"  # Deemed Exp
    B2CL = "B2C (Large)"  # NA
    EXPWP = "EXPWP"  # WPAY
    EXPWOP = "EXPWOP"  # WOPAY
    B2CS = "B2C (Others)"  # NA
    NIL_RATED = "Nil-Rated"  # Inter vs Intra & Regis vs UnRegis
    EXEMPTED = "Exempted"  # Inter vs Intra & Regis vs UnRegis
    NON_GST = "Non-GST"  # Inter vs Intra & Regis vs UnRegis
    CDNR = "CDNR"  # Like B2B
    CDNUR = "CDNUR"  # B2CL vs EXPWP vs EXPWOP
    # Other Sub-Categories
    # AT = "Advances Received"
    # TXP = "Advances Adjusted"
    # HSN = "HSN Summary"
    # DOC_ISSUE = "Document Issued"


CATEGORY_SUB_CATEGORY_MAPPING = {
    GSTR1_Categories.B2B: (
        GSTR1_SubCategories.B2B_REGULAR,
        GSTR1_SubCategories.B2B_REVERSE_CHARGE,
        GSTR1_SubCategories.SEZWP,
        GSTR1_SubCategories.SEZWOP,
        GSTR1_SubCategories.DE,
    ),
    GSTR1_Categories.B2CL: (GSTR1_SubCategories.B2CL,),
    GSTR1_Categories.EXP: (GSTR1_SubCategories.EXPWP, GSTR1_SubCategories.EXPWOP),
    GSTR1_Categories.B2CS: (GSTR1_SubCategories.B2CS,),
    GSTR1_Categories.NIL_EXEMPT: (
        GSTR1_SubCategories.NIL_RATED,
        GSTR1_SubCategories.EXEMPTED,
        GSTR1_SubCategories.NON_GST,
    ),
    GSTR1_Categories.CDNR: (GSTR1_SubCategories.CDNR,),
    GSTR1_Categories.CDNUR: (GSTR1_SubCategories.CDNUR,),
}

SUB_CATEGORIES_DESCRIPTION = {
    GSTR1_SubCategories.SEZWP: "SEZ with payment",
    GSTR1_SubCategories.SEZWOP: "SEZ without payment",
    GSTR1_SubCategories.EXPWP: "Exports with payment",
    GSTR1_SubCategories.EXPWOP: "Exports without payment",
    GSTR1_SubCategories.CDNR: "Credit/Debit Notes (Registered)",
    GSTR1_SubCategories.CDNUR: "Credit/Debit Notes (Unregistered)",
}

CATEGORY_CONDITIONS = {
    GSTR1_Categories.B2B.value: {
        "category": "is_b2b_invoice",
        "sub_category": "set_for_b2b",
    },
    GSTR1_Categories.B2CL.value: {
        "category": "is_b2cl_invoice",
        "sub_category": "set_for_b2cl",
    },
    GSTR1_Categories.EXP.value: {
        "category": "is_export_invoice",
        "sub_category": "set_for_exports",
    },
    GSTR1_Categories.B2CS.value: {
        "category": "is_b2cs_invoice",
        "sub_category": "set_for_b2cs",
    },
    GSTR1_Categories.NIL_EXEMPT.value: {
        "category": "is_nil_rated_exempted_non_gst_invoice",
        "sub_category": "set_for_nil_exp_non_gst",
    },
    GSTR1_Categories.CDNR.value: {
        "category": "is_cdnr_invoice",
        "sub_category": "set_for_cdnr",
    },
    GSTR1_Categories.CDNUR.value: {
        "category": "is_cdnur_invoice",
        "sub_category": "set_for_cdnur",
    },
}


class GSTR1Query:
    def __init__(
        self, filters=None, additional_si_columns=None, additional_si_item_columns=None
    ):
        self.si = frappe.qb.DocType("Sales Invoice")
        self.si_item = frappe.qb.DocType("Sales Invoice Item")
        self.filters = frappe._dict(filters or {})
        self.additional_si_columns = additional_si_columns or []
        self.additional_si_item_columns = additional_si_item_columns or []

    def get_base_query(self):
        returned_si = frappe.qb.DocType("Sales Invoice", alias="returned_si")

        query = (
            frappe.qb.from_(self.si)
            .inner_join(self.si_item)
            .on(self.si.name == self.si_item.parent)
            .left_join(returned_si)
            .on(self.si.return_against == returned_si.name)
            .select(
                IfNull(self.si_item.item_code, self.si_item.item_name).as_("item_code"),
                self.si_item.gst_hsn_code,
                self.si_item.uom,
                self.si.billing_address_gstin,
                self.si.company_gstin,
                self.si.customer_name,
                self.si.name.as_("invoice_no"),
                self.si.posting_date,
                IfNull(self.si.place_of_supply, "").as_("place_of_supply"),
                self.si.is_reverse_charge,
                self.si.is_export_with_gst,
                self.si.is_return,
                self.si.is_debit_note,
                self.si.return_against,
                IfNull(self.si.base_rounded_total, self.si.base_grand_total).as_(
                    "invoice_total"
                ),
                IfNull(
                    returned_si.base_rounded_total,
                    IfNull(returned_si.base_grand_total, 0),
                ).as_("returned_invoice_total"),
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
        return invoice.place_of_supply == "96-Other Countries"

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

        return (abs(invoice_total) > B2C_LIMIT) and self.is_inter_state(invoice)

    @cache_invoice_condition
    def is_b2cl_inv(self, invoice):
        return abs(invoice.invoice_total) > B2C_LIMIT and self.is_inter_state(invoice)


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


class GSTR1Subcategory(GSTR1CategoryConditions):

    def set_for_b2b(self, invoice):
        self._set_invoice_type_for_b2b_and_cdnr(invoice)

    def set_for_b2cl(self, invoice):
        # NO INVOICE VALUE
        invoice.invoice_sub_category = GSTR1_SubCategories.B2CL.value

    def set_for_exports(self, invoice):
        if invoice.is_export_with_gst:
            invoice.invoice_sub_category = GSTR1_SubCategories.EXPWP.value
            invoice.invoice_type = "WPAY"

        else:
            invoice.invoice_sub_category = GSTR1_SubCategories.EXPWOP.value
            invoice.invoice_type = "WOPAY"

    def set_for_b2cs(self, invoice):
        # NO INVOICE VALUE
        invoice.invoice_sub_category = GSTR1_SubCategories.B2CS.value

    def set_for_nil_exp_non_gst(self, invoice):
        # INVOICE TYPE
        is_registered = self.has_gstin_and_is_not_export(invoice)
        is_interstate = self.is_inter_state(invoice)

        gst_registration = "registered" if is_registered else "unregistered"
        supply_type = "Inter-State" if is_interstate else "Intra-State"

        invoice.invoice_type = f"{supply_type} to {gst_registration} persons"

        # INVOICE SUB CATEGORY
        if self.is_nil_rated(invoice):
            invoice.invoice_sub_category = GSTR1_SubCategories.NIL_RATED.value

        elif self.is_exempted(invoice):
            invoice.invoice_sub_category = GSTR1_SubCategories.EXEMPTED.value

        elif self.is_non_gst(invoice):
            invoice.invoice_sub_category = GSTR1_SubCategories.NON_GST.value

    def set_for_cdnr(self, invoice):
        self._set_invoice_type_for_b2b_and_cdnr(invoice)
        invoice.invoice_sub_category = GSTR1_SubCategories.CDNR.value

    def set_for_cdnur(self, invoice):
        invoice.invoice_sub_category = GSTR1_SubCategories.CDNUR.value
        if self.is_export(invoice):
            if invoice.is_export_with_gst:
                invoice.invoice_type = "EXPWP"
                return

            invoice.invoice_type = "EXPWOP"
            return

        invoice.invoice_type = "B2CL"
        return

    def _set_invoice_type_for_b2b_and_cdnr(self, invoice):
        if invoice.gst_category == "Deemed Export":
            invoice.invoice_type = "Deemed Exp"
            invoice.invoice_sub_category = GSTR1_SubCategories.DE.value

        elif invoice.gst_category == "SEZ":
            if invoice.is_export_with_gst:
                invoice.invoice_type = "SEZ supplies with payment"
                invoice.invoice_sub_category = GSTR1_SubCategories.SEZWP.value

            else:
                invoice.invoice_type = "SEZ supplies without payment"
                invoice.invoice_sub_category = GSTR1_SubCategories.SEZWOP.value

        elif invoice.is_reverese_charge:
            invoice.invoice_type = "Regular B2B"
            invoice.invoice_sub_category = GSTR1_SubCategories.B2B_REVERSE_CHARGE.value

        else:
            invoice.invoice_type = "Regular B2B"
            invoice.invoice_sub_category = GSTR1_SubCategories.B2B_REGULAR.value


class GSTR1Invoices(GSTR1Query, GSTR1Subcategory):
    AMOUNT_FIELDS = {
        "taxable_value": 0,
        "igst_amount": 0,
        "cgst_amount": 0,
        "sgst_amount": 0,
        "total_cess_amount": 0,
    }

    def __init__(self, filters=None):
        super().__init__(filters)

    def process_invoices(self, invoices):
        settings = frappe.get_cached_doc("GST Settings")

        for invoice in invoices:
            self.invoice_conditions = {}
            self.assign_categories(invoice)
            invoice["uom"] = get_full_gst_uom(invoice.get("uom"), settings)

    def assign_categories(self, invoice):

        self.set_invoice_category(invoice)
        self.set_invoice_sub_category_and_type(invoice)

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
                Sum(query.taxable_value).as_("taxable_value"),
                Sum(query.cgst_amount).as_("cgst_amount"),
                Sum(query.sgst_amount).as_("sgst_amount"),
                Sum(query.igst_amount).as_("igst_amount"),
                Sum(query.total_cess_amount).as_("total_cess_amount"),
                Sum(query.total_tax).as_("total_tax_amount"),
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

        return filtered_invoices

    def get_overview(self):
        final_summary = []
        sub_category_summary = self.get_sub_category_summary()

        for category, sub_categories in CATEGORY_SUB_CATEGORY_MAPPING.items():
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

        for category in GSTR1_SubCategories:
            summary[category.value] = {
                "description": SUB_CATEGORIES_DESCRIPTION.get(category, category.value),
                "no_of_records": 0,
                "indent": 1,
                "unique_records": set(),
                **self.AMOUNT_FIELDS,
            }

        for row in invoices:
            summary_row = summary[
                row.get("invoice_sub_category", row["invoice_category"])
            ]

            for key in self.AMOUNT_FIELDS:
                summary_row[key] += row[key]

            summary_row["unique_records"].add(row.invoice_no)

        for summary_row in summary.values():
            summary_row["no_of_records"] = len(summary_row["unique_records"])

        return summary

    def update_overlaping_invoice_summary(self, sub_category_summary, final_summary):
        nil_exempt_non_gst = (
            GSTR1_SubCategories.NIL_RATED.value,
            GSTR1_SubCategories.EXEMPTED.value,
            GSTR1_SubCategories.NON_GST.value,
        )

        # Get Unique Taxable Invoices
        unique_invoices = set()
        for category, row in sub_category_summary.items():
            if category in nil_exempt_non_gst:
                continue

            unique_invoices.update(row["unique_records"])

        # Get Overlaping Invoices
        overlaping_invoices = set()
        for category in nil_exempt_non_gst:
            category_invoices = sub_category_summary[category]["unique_records"]

            overlaping_invoices.update(category_invoices.intersection(unique_invoices))
            unique_invoices.update(category_invoices)

        # Update Summary
        if overlaping_invoices:
            final_summary.append(
                {
                    "description": "Overlaping Invoices in Nil-Rated/Exempt/Non-GST",
                    "no_of_records": -len(overlaping_invoices),
                }
            )
