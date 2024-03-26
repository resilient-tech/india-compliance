# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

from pypika import Order

import frappe
from frappe.query_builder.functions import IfNull, Sum
from frappe.utils import getdate

B2C_LIMIT = 2_50_000


class GSTR1Query:
    def get_invoices_for_item_wise_summary(self, filters=None):
        si = frappe.qb.DocType("Sales Invoice")
        si_item = frappe.qb.DocType("Sales Invoice Item")

        query = self.get_base_query(si, si_item)
        query = query.select(
            si_item.item_code.as_("item"),
            si_item.taxable_value,
            si_item.cgst_amount,
            si_item.sgst_amount,
            si_item.igst_amount,
            (si_item.cess_amount + si_item.cess_non_advol_amount).as_(
                "total_cess_amount"
            ),
            (
                si_item.cgst_amount
                + si_item.sgst_amount
                + si_item.igst_amount
                + si_item.cess_amount
                + si_item.cess_non_advol_amount
            ).as_("total_tax"),
            (
                si_item.taxable_value
                + si_item.cgst_amount
                + si_item.sgst_amount
                + si_item.igst_amount
                + si_item.cess_amount
                + si_item.cess_non_advol_amount
            ).as_("total_amount"),
        )
        query = self.get_query_with_filters(si, query, filters)

        return query.run(as_dict=True)

    def get_invoices_for_hsn_wise_summary(self, filters=None):
        si = frappe.qb.DocType("Sales Invoice")
        si_item = frappe.qb.DocType("Sales Invoice Item")

        query = self.get_base_query(si, si_item)
        query = query.select(
            Sum(si_item.taxable_value).as_("taxable_value"),
            Sum(si_item.cgst_amount).as_("cgst_amount"),
            Sum(si_item.sgst_amount).as_("sgst_amount"),
            Sum(si_item.igst_amount).as_("igst_amount"),
            (Sum(si_item.cess_amount) + Sum(si_item.cess_non_advol_amount)).as_(
                "total_cess_amount"
            ),
            (
                Sum(si_item.cgst_amount)
                + Sum(si_item.sgst_amount)
                + Sum(si_item.igst_amount)
                + Sum(si_item.cess_amount)
                + Sum(si_item.cess_non_advol_amount)
            ).as_("total_tax"),
            (
                Sum(si_item.taxable_value)
                + Sum(si_item.cgst_amount)
                + Sum(si_item.sgst_amount)
                + Sum(si_item.igst_amount)
                + Sum(si_item.cess_amount)
                + Sum(si_item.cess_non_advol_amount)
            ).as_("total_amount"),
        ).groupby(
            si.name,
            si_item.gst_hsn_code,
            (si_item.cgst_rate + si_item.sgst_rate + si_item.igst_rate),
            si_item.gst_treatment,
        )

        query = self.get_query_with_filters(si, query, filters)

        return query.run(as_dict=True)

    def get_base_query(self, si, si_item):
        returned_si = frappe.qb.DocType("Sales Invoice", alias="returned_si")

        query = (
            frappe.qb.from_(si)
            .inner_join(si_item)
            .on(si.name == si_item.parent)
            .left_join(returned_si)
            .on(si.return_against == returned_si.name)
            .select(
                si_item.gst_hsn_code,
                si.billing_address_gstin,
                si.company_gstin,
                si.customer_name,
                si.name.as_("invoice_no"),
                si.posting_date,
                si.place_of_supply,
                si.is_reverse_charge,
                si.is_export_with_gst,
                si.is_return,
                si.is_debit_note,
                si.return_against,
                IfNull(si.base_rounded_total, si.base_grand_total).as_("invoice_total"),
                IfNull(
                    returned_si.base_rounded_total,
                    IfNull(returned_si.base_grand_total, 0),
                ).as_("returned_invoice_total"),
                si.gst_category,
                si_item.gst_treatment,
                (si_item.cgst_rate + si_item.sgst_rate + si_item.igst_rate).as_(
                    "gst_rate"
                ),
            )
            .where(si.docstatus == 1)
            .where(si.is_opening != "Yes")
            .where(IfNull(si.billing_address_gstin, "") != si.company_gstin)
            .orderby(si.posting_date, si.name, order=Order.desc)
        )

        return query

    def get_query_with_filters(self, si, query, filters=None):
        if filters.company:
            query = query.where(si.company == filters.company)

        if filters.company_gstin:
            query = query.where(si.company_gstin == filters.company_gstin)

        if filters.date_range[0]:
            query = query.where(si.posting_date >= getdate(filters.date_range[0]))

        if filters.date_range[1]:
            query = query.where(si.posting_date <= getdate(filters.date_range[1]))

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
        return abs(invoice.invoice_total) > B2C_LIMIT and self.is_inter_state(invoice)


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


class GSTR1Overview(GSTR1Invoices):
    def get_summary_section_wise(self, description, invoices):
        summary = {}
        summary["description"] = description
        summary["no_of_records"] = len(
            set(invoice["invoice_no"] for invoice in invoices)
        )
        summary["taxable_value"] = sum(invoice["taxable_value"] for invoice in invoices)
        summary["igst_amount"] = sum(invoice["igst_amount"] for invoice in invoices)
        summary["cgst_amount"] = sum(invoice["cgst_amount"] for invoice in invoices)
        summary["sgst_amount"] = sum(invoice["sgst_amount"] for invoice in invoices)
        summary["total_cess_amount"] = sum(
            invoice["total_cess_amount"] for invoice in invoices
        )

        return summary

    def get_overview(self, filters):

        invoices = self.get_invoices_for_item_wise_summary(filters)

        b2b_regular_invoices = self.get_b2b_regular_invoices(invoices)
        b2b_reverse_charge_invoices = self.get_b2b_reverse_charge_invoices(invoices)
        b2c_large_invoices = self.get_b2cl_invoices(invoices)
        exports_with_payment_invoices = self.get_export_with_payment_invoices(invoices)
        exports_without_payment_invoices = self.get_export_without_payment_invoices(
            invoices
        )
        sez_with_payment_invoices = self.get_sez_wp_invoices(invoices)
        sez_without_payment_invoices = self.get_sez_wop_invoices(invoices)
        deemed_exports_invoices = self.get_deemed_exports_invoices(invoices)
        b2cs_invoices = self.get_b2cs_invoices(invoices)
        nil_rated_invoices = self.get_nil_rated_invoices(invoices)
        exempted_invoices = self.get_exempted_invoices(invoices)
        non_gst_invoices = self.get_non_gst_invoices(invoices)
        cdnr_invoices = self.get_cdnr_invoices(invoices)
        cdnur_invoices = self.get_cdnur_invoices(invoices)

        summary = []
        summary.append(
            self.get_summary_section_wise("B2B Regular", b2b_regular_invoices)
        )
        summary.append(
            self.get_summary_section_wise(
                "B2B Reverse Charge", b2b_reverse_charge_invoices
            )
        )
        summary.append(
            self.get_summary_section_wise("SEZ with payment", sez_with_payment_invoices)
        )
        summary.append(
            self.get_summary_section_wise(
                "SEZ without payment", sez_without_payment_invoices
            )
        )
        summary.append(
            self.get_summary_section_wise("Deemed Exports", deemed_exports_invoices)
        )
        summary.append(self.get_summary_section_wise("B2C (Large)", b2c_large_invoices))
        summary.append(
            self.get_summary_section_wise(
                "Export with payment", exports_with_payment_invoices
            )
        )
        summary.append(
            self.get_summary_section_wise(
                "Export without payment", exports_without_payment_invoices
            )
        )
        summary.append(self.get_summary_section_wise("B2C (Others)", b2cs_invoices))
        summary.append(self.get_summary_section_wise("Nil Rated", nil_rated_invoices))
        summary.append(self.get_summary_section_wise("Exempted", exempted_invoices))
        summary.append(self.get_summary_section_wise("Non-GST", non_gst_invoices))
        summary.append(
            self.get_summary_section_wise(
                "Credit / Debit notes (Registered)", cdnr_invoices
            )
        )
        summary.append(
            self.get_summary_section_wise(
                "Credit / Debit notes (Unregistered)", cdnur_invoices
            )
        )

        return summary
