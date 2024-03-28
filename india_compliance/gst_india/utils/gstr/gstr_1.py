# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

from pypika import Order

import frappe
from frappe.query_builder.functions import Date, IfNull, Sum
from frappe.utils import getdate

B2C_LIMIT = 2_50_000
SUB_CATEGORIES = {
    "B2B Regular": "B2B Regular",
    "B2B Reverse charge": "B2B Reverse Charge",
    "SEZWP": "SEZ with payment",
    "SEZWOP": "SEZ without payment",
    "Deemed Exports": "Deemed Exports",
    "B2C (Large)": "B2C (Large)",
    "EXPWP": "Exports with payment",
    "EXPWOP": "Exports without payment",
    "B2C (Others)": "B2C (Others)",
    "Nil-Rated": "Nil-Rated",
    "Exempted": "Exempted",
    "Non-GST": "Non-GST",
    "CDNR": "Credit/Debit Notes (Registered)",
    "CDNUR": "Credit/Debit Notes (Unregistered)",
}

INVOICES = {
    "B2B,SEZ,DE": {
        "B2B Regular": "self.is_b2b_regular_invoice(invoice)",
        "B2B Reverse Charge": "self.is_b2b_reverse_charge_invoice(invoice)",
        "SEZWP": "self.is_sez_wp_invoice(invoice)",
        "SEZWOP": "self.is_sez_wop_invoice(invoice)",
        "Deemed Exports": "self.is_deemed_exports_invoice(invoice)",
        "B2B,SEZ,DE": "self.is_b2b_invoice(invoice)",
    },
    "B2C (Large)": {"B2C (Large)": "self.is_b2cl_invoice(invoice)"},
    "Exports": {
        "EXPWP": "self.is_export_with_payment_invoice(invoice)",
        "EXPWOP": "self.is_export_without_payment_invoice(invoice)",
        "Exports": "self.is_export_invoice(invoice)",
    },
    "B2C (Others)": {"B2C (Others)": "self.is_b2cs_invoice(invoice)"},
    "Nil-Rated,Exempted,Non-GST": {
        "Nil-Rated": "self.is_nil_rated(invoice)",
        "Exempted": "self.is_exempted(invoice)",
        "Non-GST": "self.is_non_gst(invoice)",
        "Nil-Rated,Exempted,Non-GST": "self.is_nil_rated_exempted_non_gst_invoice(invoice)",
    },
    "Credit/Debit Notes (Registered)": {
        "CDNR": "self.is_cdnr_invoice(invoice)",
        "Credit/Debit Notes (Registered)": "self.is_cdnr_invoice(invoice)",
    },
    "Credit/Debit Notes (Unregistered)": {
        "CDNUR": "self.is_cdnur_invoice(invoice)",
        "Credit/Debit Notes (Unregistered)": "self.is_cdnur_invoice(invoice)",
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
        return (
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
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and not self.is_cn_dn(invoice)
            and self.has_gstin_and_is_not_export(invoice)
            and not invoice.is_reverese_charge
            and invoice.gst_category != "SEZ"
            and invoice.gst_category != "Deemed Export"
        )

    def is_b2b_reverse_charge_invoice(self, invoice):
        return (
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and not self.is_cn_dn(invoice)
            and self.has_gstin_and_is_not_export(invoice)
            and invoice.is_reverese_charge
            and invoice.gst_category == "Deemed Export"
        )

    def is_sez_wp_invoice(self, invoice):
        return (
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and not self.is_cn_dn(invoice)
            and self.has_gstin_and_is_not_export(invoice)
            and invoice.gst_category == "SEZ"
            and invoice.is_export_with_gst
        )

    def is_sez_wop_invoice(self, invoice):
        return (
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and not self.is_cn_dn(invoice)
            and self.has_gstin_and_is_not_export(invoice)
            and invoice.gst_category == "SEZ"
            and not invoice.is_export_with_gst
        )

    def is_deemed_exports_invoice(self, invoice):
        return (
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and not self.is_cn_dn(invoice)
            and self.has_gstin_and_is_not_export(invoice)
            and invoice.gst_category == "Deemed Export"
        )

    def is_export_invoice(self, invoice):
        return (
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and not self.is_cn_dn(invoice)
            and self.is_export(invoice)
        )

    def is_export_with_payment_invoice(self, invoice):
        return (
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and not self.is_cn_dn(invoice)
            and self.is_export(invoice)
            and invoice.is_export_with_gst
        )

    def is_export_without_payment_invoice(self, invoice):
        return (
            not self.is_nil_rated_exempted_or_non_gst(invoice)
            and not self.is_cn_dn(invoice)
            and self.is_export(invoice)
            and not invoice.is_export_with_gst
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


class GSTR1Invoices(GSTR1Query, GSTR1Sections):
    def __init__(self, filters=None):
        super().__init__(filters)

    def assign_invoice_category_and_sub_category(self, invoices):
        for invoice in invoices:
            self.invoice_conditions = {}
            if self.is_nil_rated_exempted_non_gst_invoice(invoice):
                invoice.invoice_category = "Nil-Rated,Exempted,Non-GST"

                if self.is_nil_rated(invoice):
                    invoice.invoice_sub_category = "Nil-Rated"
                    continue

                if self.is_exempted(invoice):
                    invoice.invoice_sub_category = "Exempted"
                    continue

                if self.is_non_gst(invoice):
                    invoice.invoice_sub_category = "Non-GST"
                    continue

            elif self.is_b2b_invoice(invoice):
                invoice.invoice_category = "B2B"

                if self.is_b2b_regular_invoice(invoice):
                    invoice.invoice_sub_category = "B2B Regular"
                    continue

                if self.is_b2b_reverse_charge_invoice(invoice):
                    invoice.invoice_sub_category = "B2B Reverse Charge"
                    continue

                if self.is_sez_wp_invoice(invoice):
                    invoice.invoice_sub_category = "SEZWP"
                    continue

                if self.is_sez_wop_invoice(invoice):
                    invoice.invoice_sub_category = "SEZWOP"
                    continue

                if self.is_deemed_exports_invoice(invoice):
                    invoice.invoice_sub_category = "Deemed Exports"
                    continue

            elif self.is_export_invoice(invoice):
                invoice.invoice_category = "Exports"

                if self.is_export_with_payment_invoice(invoice):
                    invoice.invoice_sub_category = "EXPWP"
                    continue

                if self.is_export_without_payment_invoice(invoice):
                    invoice.invoice_sub_category = "EXPWOP"
                    continue

            elif self.is_b2cl_invoice(invoice):
                invoice.invoice_category = "B2C (Large)"
                invoice.invoice_sub_category = "B2C (Large)"
                continue

            elif self.is_b2cs_invoice(invoice):
                invoice.invoice_category = "B2C (Others)"
                invoice.invoice_sub_category = "B2C (Others)"
                continue

            elif self.is_cdnr_invoice(invoice):
                invoice.invoice_category = "CDNR"
                invoice.invoice_sub_category = "CDNR"
                continue

            elif self.is_cdnur_invoice(invoice):
                invoice.invoice_category = "CDNUR"
                invoice.invoice_sub_category = "CDNUR"
                continue

            else:
                invoice.invoice_category = "B2C (Others)"
                invoice.invoice_sub_category = "B2C (Others)"

        return invoices

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
        condition_func = INVOICES[invoice_category][
            invoice_sub_category or invoice_category
        ]
        filtered_invoices = []
        for invoice in invoices:
            self.invoice_conditions = {}
            if eval(condition_func):
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

        for category, description in SUB_CATEGORIES.items():
            summary[category] = {
                "description": description,
                "no_of_records": 0,
                **amount_fields,
            }

        for row in invoices:
            new_row = summary[row.get("invoice_sub_category", row["invoice_category"])]

            for key in amount_fields:
                new_row[key] += row[key]

            new_row["no_of_records"] += 1

        return list(summary.values())
