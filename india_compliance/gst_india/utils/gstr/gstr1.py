# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

from pypika import Order

import frappe
from frappe.query_builder.functions import Date, IfNull, Sum
from frappe.utils import getdate

B2C_LIMIT = 2_50_000
SUB_CATEGORIES = {
    "B2B Regular": "B2B Regular",
    "B2B Reverce Charge": "B2B Reverse Charge",
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
    "CDNR": "Credit/Debit notes (Registered)",
    "CDNUR": "Credit/Debit notes (Unregistered)",
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


class GSTR1Conditions:

    def is_nil_rated(self, invoice):
        return invoice.gst_treatment == "Nil-Rated"

    def is_exempted(self, invoice):
        return invoice.gst_treatment == "Exempted"

    def is_non_gst(self, invoice):
        return invoice.gst_treatment == "Non-GST"

    def is_nil_rated_exempted_or_non_gst(self, invoice):
        return (
            self.is_nil_rated(invoice)
            or self.is_exempted(invoice)
            or self.is_non_gst(invoice)
        )

    def is_cn_dn(self, invoice):
        return invoice.is_return or invoice.is_debit_note

    def has_gstin_and_is_not_export(self, invoice):
        return invoice.billing_address_gstin and not self.is_export(invoice)

    def is_export(self, invoice):
        return invoice.place_of_supply == "96-Other Countries"

    def is_inter_state(self, invoice):
        return invoice.company_gstin[:2] != invoice.place_of_supply[:2]

    def is_b2cl_cn_dn(self, invoice):
        invoice_total = (
            max(abs(invoice.invoice_total), abs(invoice.returned_invoice_total))
            if invoice.return_against
            else invoice.invoice_total
        )

        return (abs(invoice_total) > B2C_LIMIT) and self.is_inter_state(invoice)

    def is_b2cl_invoice(self, invoice):
        return abs(invoice.total_amount) > B2C_LIMIT and self.is_inter_state(invoice)


class GSTR1Sections(GSTR1Conditions):
    def get_nil_rated_exempted_non_gst_invoices(self, invoices):
        filtered_invoices = []
        for invoice in invoices:
            if (
                self.is_nil_rated(invoice)
                or self.is_exempted(invoice)
                or self.is_non_gst(invoice)
            ):
                filtered_invoices.append(invoice)

        return filtered_invoices

    def get_nil_rated_invoices(self, invoices):
        filtered_invoices = []
        for invoice in invoices:
            if self.is_nil_rated(invoice):
                filtered_invoices.append(invoice)

        return filtered_invoices

    def get_exempted_invoices(self, invoices):
        filtered_invoices = []
        for invoice in invoices:
            if self.is_exempted(invoice):
                filtered_invoices.append(invoice)

        return filtered_invoices

    def get_non_gst_invoices(self, invoices):
        filtered_invoices = []
        for invoice in invoices:
            if self.is_non_gst(invoice):
                filtered_invoices.append(invoice)

        return filtered_invoices

    def get_b2b_invoices(self, invoices):
        filtered_invoices = []

        for invoice in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(invoice)
                and not self.is_cn_dn(invoice)
                and self.has_gstin_and_is_not_export(invoice)
            ):
                filtered_invoices.append(invoice)

        return filtered_invoices

    def get_b2b_regular_invoices(self, invoices):
        filtered_invoices = []

        for invoice in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(invoice)
                and not self.is_cn_dn(invoice)
                and self.has_gstin_and_is_not_export(invoice)
                and not invoice.is_reverese_charge
                and invoice.gst_category != "SEZ"
                and invoice.gst_category != "Deemed Export"
            ):
                filtered_invoices.append(invoice)

        return filtered_invoices

    def get_b2b_reverse_charge_invoices(self, invoices):
        filtered_invoices = []

        for invoice in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(invoice)
                and not self.is_cn_dn(invoice)
                and self.has_gstin_and_is_not_export(invoice)
                and invoice.is_reverese_charge
                and invoice.gst_category == "Deemed Export"
            ):
                filtered_invoices.append(invoice)

        return filtered_invoices

    def get_sez_wp_invoices(self, invoices):
        filtered_invoices = []

        for invoice in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(invoice)
                and not self.is_cn_dn(invoice)
                and self.has_gstin_and_is_not_export(invoice)
                and invoice.gst_category == "SEZ"
                and invoice.is_export_with_gst
            ):
                filtered_invoices.append(invoice)

        return filtered_invoices

    def get_sez_wop_invoices(self, invoices):
        filtered_invoices = []

        for invoice in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(invoice)
                and not self.is_cn_dn(invoice)
                and self.has_gstin_and_is_not_export(invoice)
                and invoice.gst_category == "SEZ"
                and not invoice.is_export_with_gst
            ):
                filtered_invoices.append(invoice)

        return filtered_invoices

    def get_deemed_exports_invoices(self, invoices):
        filtered_invoices = []

        for invoice in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(invoice)
                and not self.is_cn_dn(invoice)
                and self.has_gstin_and_is_not_export(invoice)
                and invoice.gst_category == "Deemed Export"
            ):
                filtered_invoices.append(invoice)

        return filtered_invoices

    def get_export_invoices(self, invoices):
        filtered_invoices = []

        for invoice in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(invoice)
                and not self.is_cn_dn(invoice)
                and self.is_export(invoice)
            ):
                filtered_invoices.append(invoice)

        return filtered_invoices

    def get_export_with_payment_invoices(self, invoices):
        filtered_invoices = []
        for invoice in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(invoice)
                and not self.is_cn_dn(invoice)
                and self.is_export(invoice)
                and invoice.is_export_with_gst
            ):
                filtered_invoices.append(invoice)

        return filtered_invoices

    def get_export_without_payment_invoices(self, invoices):
        filtered_invoices = []
        for invoice in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(invoice)
                and not self.is_cn_dn(invoice)
                and self.is_export(invoice)
                and not invoice.is_export_with_gst
            ):
                filtered_invoices.append(invoice)

        return filtered_invoices

    def get_b2cl_invoices(self, invoices):
        filtered_invoices = []

        for invoice in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(invoice)
                and not self.is_cn_dn(invoice)
                and not self.has_gstin_and_is_not_export(invoice)
                and not self.is_export(invoice)
                and self.is_b2cl_invoice(invoice)
            ):
                filtered_invoices.append(invoice)

        return filtered_invoices

    def get_b2cs_invoices(self, invoices):
        filtered_invoices = []

        for invoice in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(invoice)
                and not self.has_gstin_and_is_not_export(invoice)
                and not self.is_export(invoice)
                and (
                    not self.is_b2cl_cn_dn(invoice) or not self.is_b2cl_invoice(invoice)
                )
            ):
                filtered_invoices.append(invoice)

        return filtered_invoices

    def get_cdnr_invoices(self, invoices):
        filtered_invoices = []

        for invoice in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(invoice)
                and self.is_cn_dn(invoice)
                and self.has_gstin_and_is_not_export(invoice)
            ):
                filtered_invoices.append(invoice)

        return filtered_invoices

    def get_cdnur_invoices(self, invoices):
        filtered_invoices = []

        for invoice in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(invoice)
                and self.is_cn_dn(invoice)
                and not self.has_gstin_and_is_not_export(invoice)
                and (self.is_export(invoice) or self.is_b2cl_cn_dn(invoice))
            ):
                filtered_invoices.append(invoice)

        return filtered_invoices


class GSTR1Invoices(GSTR1Query, GSTR1Sections):
    def __init__(self, filters=None):
        super().__init__(filters)

    def assign_invoice_category_and_sub_category(self, invoices):
        for invoice in invoices:
            if (
                invoice.gst_treatment == "Nil-Rated"
                or invoice.gst_treatment == "Exempted"
                or invoice.gst_treatment == "Non-GST"
            ):
                invoice.invoice_category = "Nil-Rated,Exempted,Non-GST"

                if invoice.gst_treatment == "Nil-Rated":
                    invoice.invoice_sub_category = "Nil-Rated"
                    continue

                if invoice.gst_treatment == "Exempted":
                    invoice.invoice_sub_category = "Exempted"
                    continue

                if invoice.gst_treatment == "Non-GST":
                    invoice.invoice_sub_category = "Non-GST"
                    continue

            if not self.is_cn_dn(invoice):
                if self.has_gstin_and_is_not_export(invoice):
                    invoice.invoice_category = "B2B"

                    if invoice.is_reverse_charge:
                        invoice.invoice_sub_category = "B2B Reverse charge"
                        continue

                    if invoice.gst_category == "SEZ":
                        if invoice.is_export_with_gst:
                            invoice.invoice_sub_category = "SEZWP"
                            continue
                        else:
                            invoice.invoice_category = "SEZWOP"
                            continue

                    if invoice.gst_category == "Deemed Exports":
                        invoice.invoice_sub_category = "Deemed Exports"
                        continue

                    invoice.invoice_sub_category = "B2B Regular"
                    continue

                if self.is_export(invoice):
                    invoice.invoice_category = "Exports"

                    if invoice.is_export_with_gst:
                        invoice.invoice_sub_category = "EXPWP"
                        continue

                    invoice.invoice_sub_category = "EXPWOP"
                    continue

                if self.is_b2cl_invoice(invoice):
                    invoice.invoice_category = "B2C (Large)"
                    continue

                invoice.invoice_category = "B2C (Others)"
                continue

            else:
                if self.has_gstin_and_is_not_export(invoice):
                    invoice.invoice_category = "CDNR"
                    continue

                if self.is_export(invoice) or self.is_b2cl_cn_dn(invoice):
                    invoice.invoice_category = "CDNUR"
                    continue

                invoice.invoice_category = "B2C (Others)"

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
        if not invoice_category:
            return invoices

        if invoice_category == "Nil Rated,Exempted,Non-GST":
            if not invoice_sub_category:
                return self.get_nil_rated_exempted_non_gst_invoices(invoices)

            if invoice_sub_category == "Nil-Rated":
                return self.get_nil_rated_invoices(invoices)

            if invoice_sub_category == "Exempted":
                return self.get_exempted_invoices(invoices)

            if invoice_sub_category == "Non-GST":
                return self.get_non_gst_invoices(invoices)

        if invoice_category == "B2B,SEZ,DE":
            if not invoice_sub_category:
                return self.get_b2b_invoices(invoices)

            if invoice_sub_category == "B2B Regular":
                return self.get_b2b_regular_invoices(invoices)

            if invoice_sub_category == "B2B Reverse charge":
                return self.get_b2b_reverse_charge_invoices(invoices)

            if invoice_sub_category == "SEZWP":
                return self.get_sez_wp_invoices(invoices)

            if invoice_sub_category == "SEZWOP":
                return self.get_sez_wop_invoices(invoices)

            if invoice_sub_category == "Deemed Exports":
                return self.get_deemed_exports_invoices(invoices)

        if invoice_category == "Exports":
            if not invoice_sub_category:
                return self.get_export_invoices(invoices)

            if invoice_sub_category == "EXPWP":
                return self.get_export_with_payment_invoices(invoices)

            if invoice_sub_category == "EXPWOP":
                return self.get_export_without_payment_invoices(invoices)

        if invoice_category == "B2C (Large)":
            return self.get_b2cl_invoices(invoices)

        if invoice_category == "B2C (Others)":
            return self.get_b2cs_invoices(invoices)

        if invoice_category == "Credit / Debit notes (Registered)":
            return self.get_cdnr_invoices(invoices)

        if invoice_category == "Credit / Debit Notes (Unregistered)":
            return self.get_cdnur_invoices(invoices)

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
