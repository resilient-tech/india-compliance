# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

from pypika import Order

import frappe
from frappe.query_builder.functions import Date, IfNull, Sum
from frappe.utils import getdate

B2C_LIMIT = 2_50_000

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
DOCUMENT_TYPE_MAP = {
    "B2B,SEZ,DE": "get_category_for_b2b",
    "B2C (Large)": "get_category_for_b2cl",
    "Exports": "get_category_for_exports",
    "B2C (Others)": "get_category_for_b2c",
    "Nil-Rated,Exempted,Non-GST": "get_category_for_nil_exp_non_gst",
    "Credit/Debit Notes (Registered)": "get_category_for_cdnr",
    "Credit/Debit Notes (Unregistered)": "get_category_for_cdnur",
}

SUB_CATEGORY_CONDITIONS = {
    "B2B,SEZ,DE": {
        "B2B Regular": "is_b2b_regular_invoice",
        "B2B Reverse Charge": "is_b2b_reverse_charge_invoice",
        "SEZWP": "is_sez_wp_invoice",
        "SEZWOP": "is_sez_wop_invoice",
        "Deemed Exports": "is_deemed_exports_invoice",
    },
    "B2C (Large)": {"B2C (Large)": "is_b2cl_invoice"},
    "Exports": {
        "EXPWP": "is_export_with_payment_invoice",
        "EXPWOP": "is_export_without_payment_invoice",
    },
    "B2C (Others)": {"B2C (Others)": "is_b2cs_invoice"},
    "Nil-Rated,Exempted,Non-GST": {
        "Nil-Rated": "is_nil_rated_invoice",
        "Exempted": "is_exempted_invoice",
        "Non-GST": "is_non_gst_invoice",
    },
    "Credit/Debit Notes (Registered)": {
        "CDNR": "is_cdnr_invoice",
    },
    "Credit/Debit Notes (Unregistered)": {
        "CDNUR": "is_cdnur_invoice",
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

    def is_nil_rated_invoice(self, invoice):
        return self.is_nil_rated(invoice)

    def is_exempted_invoice(self, invoice):
        return self.is_exempted(invoice)

    def is_non_gst_invoice(self, invoice):
        return self.is_non_gst(invoice)

    def is_b2b_invoice(self, invoice):
        return (
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and not self.is_cn_dn(invoice)
            and self.has_gstin_and_is_not_export(invoice)
        )

    def is_b2b_regular_invoice(self, invoice):
        return (
            self.is_b2b_invoice(invoice)
            and not invoice.is_reverese_charge
            and invoice.gst_category != "SEZ"
            and invoice.gst_category != "Deemed Export"
        )

    def is_b2b_reverse_charge_invoice(self, invoice):
        return self.is_b2b_invoice(invoice) and invoice.is_reverese_charge

    def is_sez_wp_invoice(self, invoice):
        return (
            self.is_b2b_invoice(invoice)
            and invoice.gst_category == "SEZ"
            and invoice.is_export_with_gst
        )

    def is_sez_wop_invoice(self, invoice):
        return (
            self.is_b2b_invoice(invoice)
            and invoice.gst_category == "SEZ"
            and not invoice.is_export_with_gst
        )

    def is_deemed_exports_invoice(self, invoice):
        return self.is_b2b_invoice(invoice) and invoice.gst_category == "Deemed Export"

    def is_export_invoice(self, invoice):
        return (
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and not self.is_cn_dn(invoice)
            and self.is_export(invoice)
        )

    def is_export_with_payment_invoice(self, invoice):
        return self.is_export_invoice(invoice) and invoice.is_export_with_gst

    def is_export_without_payment_invoice(self, invoice):
        return self.is_export_invoice(invoice) and not invoice.is_export_with_gst

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

    def is_b2b_supply(self, invoice):
        return


class GSTRDocumentType(GSTR1Sections):
    def get_category_for_b2b(self, invoice):
        if self.is_sez_wp_invoice(invoice):
            return "SEZ supplies with payment"

        elif self.is_sez_wop_invoice(invoice):
            return "SEZ supplies without payment"

        elif self.is_deemed_exports_invoice(invoice):
            return "Deemed Exp"

        return "Regular B2B"

    def get_category_for_b2cl(self, invoice):
        # NO value
        return ""

    def get_category_for_exports(self, invoice):
        if self.is_export_with_payment_invoice(invoice):
            return "WPAY"

        return "WOPAY"

    def get_category_for_b2c(self, invoice):
        # No value
        return ""

    def get_category_for_nil_exp_non_gst(self, invoice):
        is_registered = self.has_gstin_and_is_not_export(invoice)
        is_interstate = self.is_inter_state(invoice)

        gst_registration = "registered" if is_registered else "unregistered"
        supply_type = "Inter-State" if is_interstate else "Intra-State"

        return f"{supply_type} to {gst_registration} persons"

    def get_category_for_cdnr(self, invoice):
        if invoice.gst_category == "Deemed Export":
            return "Deemed Exp"

        elif invoice.gst_category == "SEZ":
            if invoice.is_export_with_gst:
                return "SEZ supplies with payment"

            return "SEZ supplies without payment"

        elif invoice.is_reverese_charge:
            # TODO: verify
            return "Intra-State supplies attracting IGST"

        return "Regular B2B"

    def get_category_for_cdnur(self, invoice):
        if self.is_export(invoice):
            if invoice.is_export_with_gst:
                return "EXPWP"

            return "EXPWOP"

        return "B2CL"


class GSTR1Invoices(GSTR1Query, GSTRDocumentType):
    def __init__(self, filters=None):
        super().__init__(filters)

    def set_additional_fields(self, invoices):
        for invoice in invoices:
            self.invoice_conditions = {}
            self.assign_categories(invoice)

        return invoices

    def assign_categories(self, invoice):

        invoice.invoice_category = self.get_invoice_category(invoice)
        invoice.invoice_sub_category = self.get_invoice_sub_category(invoice)
        invoice.invoice_type = self.get_invoice_type(invoice)

    def get_invoice_category(self, invoice):
        for category, function in CATEGORY_CONDITIONS.items():
            if getattr(self, function, None)(invoice):
                return category

    def get_invoice_type(self, invoice):
        func = DOCUMENT_TYPE_MAP.get(invoice.invoice_category)

        print(getattr(self, func, None)(invoice))
        return getattr(self, func, None)(invoice)

    def get_invoice_sub_category(self, invoice):
        sub_category_conditions = SUB_CATEGORY_CONDITIONS.get(invoice.invoice_category)
        for sub_category, function in sub_category_conditions.items():
            if getattr(self, function, None)(invoice):
                return sub_category

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

        if invoice_sub_category:
            condition = SUB_CATEGORY_CONDITIONS.get(invoice_category).get(
                invoice_sub_category
            )

        condition = getattr(self, condition, None)

        for invoice in invoices:
            self.invoice_conditions = {}
            if not condition(invoice):
                continue

            self.assign_categories(invoice)
            filtered_invoices.append(invoice)

        return filtered_invoices

    def get_overview(self):
        invoices = self.get_invoices_for_item_wise_summary()
        invoices = self.assign_invoice_category_and_sub_category(invoices)

        amount_fields = {
            "taxable_value": 0,
            "igst_amount": 0,
            "cgst_amount": 0,
            "sgst_amount": 0,
            "total_cess_amount": 0,
        }

        summary = {}

        subcategories = []
        for subcategory_dict in SUB_CATEGORY_CONDITIONS.values():
            subcategories.extend(subcategory_dict.keys())

        for category in subcategories:
            summary[category] = {
                "description": SUB_CATEGORIES_DESCRIPTION.get(category, category),
                "no_of_records": 0,
                **amount_fields,
            }

        for row in invoices:
            new_row = summary[row.get("invoice_sub_category", row["invoice_category"])]

            for key in amount_fields:
                new_row[key] += row[key]

            new_row["no_of_records"] += 1

        return list(summary.values())
