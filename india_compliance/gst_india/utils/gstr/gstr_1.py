# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

from enum import Enum

from pypika import Order

import frappe
from frappe.query_builder.functions import Date, IfNull, Sum
from frappe.utils import getdate

B2C_LIMIT = 2_50_000


class GSTR1_Categories(Enum):
    """
    Overview Page of GSTR-1
    """

    # Invoice Items Bifurcation
    B2B = "B2B,SEZ,DE"
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


SUB_CATEGORIES_DESCRIPTION = {
    "SEZWP": "SEZ with payment",
    "SEZWOP": "SEZ without payment",
    "EXPWP": "Exports with payment",
    "EXPWOP": "Exports without payment",
    "CDNR": "Credit/Debit Notes (Registered)",
    "CDNUR": "Credit/Debit Notes (Unregistered)",
}

CATEGORY_CONDITIONS = {
    "B2B,SEZ,DE": "is_b2b_invoice",
    "B2C (Large)": "is_b2cl_invoice",
    "Exports": "is_export_invoice",
    "B2C (Others)": "is_b2cs_invoice",
    "Nil-Rated,Exempted,Non-GST": "is_nil_rated_exempted_non_gst_invoice",
    "Credit/Debit Notes (Registered)": "is_cdnr_invoice",
    "Credit/Debit Notes (Unregistered)": "is_cdnur_invoice",
}

SUB_CATEGORY_AND_INVOICE_TYPE_MAP = {
    "B2B,SEZ,DE": "set_for_b2b",
    "B2C (Large)": "set_for_b2cl",
    "Exports": "set_for_exports",
    "B2C (Others)": "set_for_b2cs",
    "Nil-Rated,Exempted,Non-GST": "set_for_nil_exp_non_gst",
    "Credit/Debit Notes (Registered)": "set_for_cdnr",
    "Credit/Debit Notes (Unregistered)": "set_for_cdnur",
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
                self.si.billing_address_gstin,
                self.si.company_gstin,
                self.si.customer_name,
                self.si.name.as_("invoice_no"),
                self.si.posting_date,
                self.si.place_of_supply,
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


def wrapper(func):
    def wrapped(self, invoice):
        if (cond := self.invoice_conditions.get(func.__name__)) is not None:
            return cond

        cond = func(self, invoice)
        self.invoice_conditions[func.__name__] = cond
        return cond

    return wrapped


class GSTR1Conditions:

    @wrapper
    def is_nil_rated(self, invoice):
        return invoice.gst_treatment == "Nil-Rated"

    @wrapper
    def is_exempted(self, invoice):
        return invoice.gst_treatment == "Exempted"

    @wrapper
    def is_non_gst(self, invoice):
        return invoice.gst_treatment == "Non-GST"

    @wrapper
    def is_nil_rated_exempted_or_non_gst(self, invoice):
        return not self.is_export(invoice) and (
            self.is_nil_rated(invoice)
            or self.is_exempted(invoice)
            or self.is_non_gst(invoice)
        )

    @wrapper
    def is_cn_dn(self, invoice):
        return invoice.is_return or invoice.is_debit_note

    @wrapper
    def has_gstin_and_is_not_export(self, invoice):
        return invoice.billing_address_gstin and not self.is_export(invoice)

    @wrapper
    def is_export(self, invoice):
        return invoice.place_of_supply == "96-Other Countries"

    @wrapper
    def is_inter_state(self, invoice):
        return invoice.company_gstin[:2] != invoice.place_of_supply[:2]

    @wrapper
    def is_b2cl_cn_dn(self, invoice):
        invoice_total = (
            max(abs(invoice.invoice_total), abs(invoice.returned_invoice_total))
            if invoice.return_against
            else invoice.invoice_total
        )

        return (abs(invoice_total) > B2C_LIMIT) and self.is_inter_state(invoice)

    @wrapper
    def is_b2cl_invoice(self, invoice):
        return abs(invoice.total_amount) > B2C_LIMIT and self.is_inter_state(invoice)


class GSTR1Sections(GSTR1Conditions):
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
        )

    def is_b2cs_invoice(self, invoice):
        return (
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and not self.has_gstin_and_is_not_export(invoice)
            and not self.is_export(invoice)
            and (not self.is_b2cl_cn_dn(invoice) or not self.is_b2cl_invoice(invoice))
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


class GSTRDocumentType(GSTR1Sections):

    def set_for_b2b(self, invoice):
        self._set_invoice_type_for_b2b_and_cdnr(invoice)

    def set_for_b2cl(self, invoice):
        # NO INVOICE VALUE
        invoice.invoice_sub_category = "B2C (Large)"

    def set_for_exports(self, invoice):
        if invoice.is_export_with_gst:
            invoice.invoice_sub_category = "EXPWP"
            invoice.invoice_type = "WPAY"

        else:
            invoice.invoice_sub_category = "EXPWOP"
            invoice.invoice_type = "WOPAY"

    def set_for_b2cs(self, invoice):
        # NO INVOICE VALUE
        invoice.invoice_sub_category = "B2C (Others)"

    def set_for_nil_exp_non_gst(self, invoice):
        # INVOICE TYPE
        is_registered = self.has_gstin_and_is_not_export(invoice)
        is_interstate = self.is_inter_state(invoice)

        gst_registration = "registered" if is_registered else "unregistered"
        supply_type = "Inter-State" if is_interstate else "Intra-State"

        invoice.invoice_type = f"{supply_type} to {gst_registration} persons"

        # INVOICE SUB CATEGORY
        if self.is_nil_rated(invoice):
            invoice.invoice_sub_category = "Nil-Rated"

        elif self.is_exempted(invoice):
            invoice.invoice_sub_category = "Exempted"

        elif self.is_non_gst(invoice):
            invoice.invoice_sub_category = "Non-GST"

    def set_for_cdnr(self, invoice):
        self._set_invoice_type_for_b2b_and_cdnr(invoice)
        invoice.invoice_sub_category = "CDNR"

    def set_for_cdnur(self, invoice):
        invoice.invoice_sub_category = "CDNUR"
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
            invoice.invoice_sub_category = "Deemed Export"

        elif invoice.gst_category == "SEZ":
            if invoice.is_export_with_gst:
                invoice.invoice_type = "SEZ supplies with payment"
                invoice.invoice_sub_category = "SEZWP"

            else:
                invoice.invoice_type = "SEZ supplies without payment"
                invoice.invoice_sub_category = "SEZWOP"

        elif invoice.is_reverese_charge:
            invoice.invoice_type = "Regular B2B"
            invoice.invoice_sub_category = "B2B Reverse Charge"

        else:
            invoice.invoice_type = "Regular B2B"
            invoice.invoice_sub_category = "B2B Regular"


class GSTR1Invoices(GSTR1Query, GSTRDocumentType):
    def __init__(self, filters=None):
        super().__init__(filters)

    def set_additional_fields(self, invoices):
        for invoice in invoices:
            self.invoice_conditions = {}
            self.assign_categories(invoice)

    def assign_categories(self, invoice):

        self.set_invoice_category(invoice)
        self.set_invoice_sub_category_and_type(invoice)

    def set_invoice_category(self, invoice):
        for category, function in CATEGORY_CONDITIONS.items():
            if getattr(self, function, None)(invoice):
                invoice.invoice_category = category

    def set_invoice_sub_category_and_type(self, invoice):
        category = invoice.invoice_category
        function = SUB_CATEGORY_AND_INVOICE_TYPE_MAP.get(category)
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
            )
            .orderby(query.posting_date, query.invoice_no, order=Order.desc)
        )

        return query.run(as_dict=True)

    def get_filtered_invoices(
        self, invoices, invoice_category=None, invoice_sub_category=None
    ):

        filtered_invoices = []
        condition = CATEGORY_CONDITIONS.get(invoice_category)
        condition = getattr(self, condition, None)

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
                continue

        return filtered_invoices

    def get_overview(self):
        invoices = self.get_invoices_for_item_wise_summary()
        self.set_additional_fields(invoices)

        amount_fields = {
            "taxable_value": 0,
            "igst_amount": 0,
            "cgst_amount": 0,
            "sgst_amount": 0,
            "total_cess_amount": 0,
        }

        summary = {}

        subcategories = [category.value for category in GSTR1_SubCategories]
        for category in subcategories:
            summary[category] = {
                "description": SUB_CATEGORIES_DESCRIPTION.get(category, category),
                "no_of_records": 0,
                "unique_records": set(),
                **amount_fields,
            }

        for row in invoices:
            category_key = summary[
                row.get("invoice_sub_category", row["invoice_category"])
            ]

            for key in amount_fields:
                category_key[key] += row[key]

            category_key["unique_records"].add(row.invoice_no)

        for category_key in summary.values():
            category_key["no_of_records"] = len(category_key["unique_records"])

        return list(summary.values())
