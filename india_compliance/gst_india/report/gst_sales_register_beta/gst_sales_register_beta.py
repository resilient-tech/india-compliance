# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Sum
from frappe.utils import getdate

B2C_LIMIT = 2_50_000


def execute(filters=None):
    if not filters:
        return [], []

    filters = frappe._dict(filters)

    if filters.from_date and filters.to_date:
        if getdate(filters.from_date) > getdate(filters.to_date):
            frappe.throw(_("The end date cannot precede the start date"))

    columns = get_columns(filters)
    invoices = []

    if filters.summary_by == "Summary by Item":
        invoices = get_invoices_for_item_wise_summary(filters)
    elif filters.summary_by == "Summary by HSN":
        invoices = get_invoices_for_hsn_wise_summary(filters)

    _class = GSTR1Invoices()

    if filters.invoice_category:
        invoices = _class.get_filtered_invoices(invoices, filters.invoice_category)
    else:
        invoices = _class.assign_invoice_category(invoices)

    return columns, invoices


def get_columns(filters):
    columns = []

    if not filters.company_gstin:
        columns.append(
            {
                "label": _("Company GSTIN"),
                "fieldname": "company_gstin",
                "width": 180,
            },
        )

    columns.extend(
        [
            {
                "label": _("Posting Date"),
                "fieldname": "posting_date",
                "width": 120,
            },
            {
                "label": _("Invoice Number"),
                "fieldname": "invoice_no",
                "fieldtype": "Link",
                "options": "Sales Invoice",
                "width": 150,
            },
            {
                "label": _("Customer Name"),
                "fieldname": "customer_name",
                "fieldtype": "Link",
                "options": "Customer",
                "width": 150,
            },
            {
                "label": _("GST Category"),
                "fieldname": "gst_category",
                "width": 120,
            },
            {
                "label": _("Billing Address GSTIN"),
                "fieldname": "billing_address_gstin",
                "width": 180,
            },
            {
                "label": _("Place of Supply"),
                "fieldname": "place_of_supply",
                "width": 120,
            },
        ]
    )

    gst_settings = frappe.get_doc("GST Settings")

    if gst_settings.enable_reverse_charge_in_sales:
        columns.append(
            {
                "label": _("Is Reverse Charge"),
                "fieldname": "is_reverse_charge",
                "fieldtype": "Check",
                "width": 120,
            }
        )

    if gst_settings.enable_overseas_transactions:
        columns.append(
            {
                "label": _("Is Export with GST"),
                "fieldname": "is_export_with_gst",
                "fieldtype": "Check",
                "width": 120,
            }
        )

    columns.extend(
        [
            {
                "label": _("Is Return"),
                "fieldname": "is_return",
                "fieldtype": "Check",
                "width": 120,
            },
            {
                "label": _("Is Debit Note"),
                "fieldname": "is_debit_note",
                "fieldtype": "Check",
                "width": 120,
            },
        ]
    )

    if filters.summary_by == "Summary by Item":
        columns.append(
            {
                "label": _("Item Code"),
                "fieldname": "item",
                "fieldtype": "Link",
                "options": "Item",
                "width": 180,
            }
        )

    columns.extend(
        [
            {
                "label": _("HSN Code"),
                "fieldname": "gst_hsn_code",
                "fieldtype": "Link",
                "options": "GST HSN Code",
                "width": 120,
            },
            {"label": _("Taxable Value"), "fieldname": "taxable_value", "width": 120},
            {"label": _("GST Treatment"), "fieldname": "gst_treatment", "width": 120},
            {"label": _("GST Rate"), "fieldname": "gst_rate", "width": 120},
            {"label": _("CGST Amount"), "fieldname": "cgst_amount", "width": 120},
            {"label": _("SGST Amount"), "fieldname": "sgst_amount", "width": 120},
            {"label": _("IGST Amount"), "fieldname": "igst_amount", "width": 120},
            {
                "label": _("Total Cess Amount"),
                "fieldname": "total_cess_amount",
                "width": 120,
            },
            {"label": _("Total Tax"), "fieldname": "total_tax", "width": 120},
            {"label": _("Tot"), "fieldname": "tot", "width": 120},
            {"label": _("Tot"), "fieldname": "return_against", "width": 120},
            {"label": _("Total Amount"), "fieldname": "total_amount", "width": 120},
        ]
    )
    if not filters.invoice_category:
        columns.append(
            {
                "label": _("Invoice Category"),
                "fieldname": "invoice_category",
                "width": 120,
            }
        )
    return columns


def get_invoices_for_item_wise_summary(filters=None):
    si = frappe.qb.DocType("Sales Invoice")
    si_item = frappe.qb.DocType("Sales Invoice Item")

    query = get_base_query(si, si_item)
    query = query.select(
        si_item.item_code.as_("item"),
        si_item.taxable_value,
        si_item.cgst_amount,
        si_item.sgst_amount,
        si_item.igst_amount,
        (si_item.cess_amount + si_item.cess_non_advol_amount).as_("total_cess_amount"),
        (si_item.cgst_amount + si_item.sgst_amount + si_item.igst_amount).as_(
            "total_tax"
        ),
        (
            si_item.taxable_value
            + si_item.cgst_amount
            + si_item.sgst_amount
            + si_item.igst_amount
            + si_item.cess_amount
            + si_item.cess_non_advol_amount
        ).as_("total_amount"),
    )
    query = get_query_with_filters(si, query, filters)
    return query.run(as_dict=True)


def get_invoices_for_hsn_wise_summary(filters=None):
    si = frappe.qb.DocType("Sales Invoice")
    si_item = frappe.qb.DocType("Sales Invoice Item")

    query = get_base_query(si, si_item)
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

    query = get_query_with_filters(si, query, filters)
    # print(query)
    return query.run(as_dict=True)


def get_base_query(si, si_item):
    query = (
        frappe.qb.from_(si)
        .inner_join(si_item)
        .on(si.name == si_item.parent)
        .select(
            si_item.gst_hsn_code,
            si.billing_address_gstin,
            si.company_gstin,
            si.customer_name,
            si.name.as_("invoice_no"),
            si.total,
            si.posting_date,
            si.place_of_supply,
            si.is_reverse_charge,
            si.is_export_with_gst,
            si.is_return,
            si.is_debit_note,
            si.return_against,
            si.gst_category,
            si_item.gst_treatment,
            Case()
            .when(
                (
                    (si.is_return == 1 or si.is_debit_note == 1)
                    and (si.return_against != "")
                ),
                frappe.qb.from_(si)
                .select(si.total)
                .where(si.name == si.return_against),
            )
            .as_("tot"),
            (si_item.cgst_rate + si_item.sgst_rate + si_item.igst_rate).as_("gst_rate"),
        )
        .where(si.docstatus == 1)
        .where(si.is_opening != "Yes")
    )
    frappe.errprint(query)
    return query


def get_query_with_filters(si, query, filters=None):
    if filters.company:
        query = query.where(si.company == filters.company)

    if filters.company_gstin:
        query = query.where(si.company_gstin == filters.company_gstin)

    if filters.from_date:
        query = query.where(si.posting_date >= getdate(filters.from_date))

    if filters.to_date:
        query = query.where(si.posting_date <= getdate(filters.to_date))

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
        # if invoice.return_against:
        #     doc = frappe.get_doc("Sales Invoice", invoice.return_against)
        #     invoice_value = max(doc.total, invoice.total)
        #     return invoice_value > B2C_LIMIT and self.is_inter_state(invoice)

        # return invoice.total > B2C_LIMIT and self.is_inter_state(invoice)
        return self.is_inter_state(invoice)

    def is_b2cl_invoice(self, invoice):
        return invoice.total > B2C_LIMIT and self.is_inter_state(invoice)


class GSTR1Sections(GSTR1Conditions):

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

        for row in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(row)
                and not self.has_gstin_and_is_not_export(row)
                and not self.is_export(row)
                and (not self.is_b2cl_cn_dn(row) or not self.is_b2cl_invoice(row))
            ):
                filtered_invoices.append(row)

        return filtered_invoices

    def get_cdnr_invoices(self, invoices):
        filtered_invoices = []

        for row in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(row)
                and self.is_cn_dn(row)
                and self.has_gstin_and_is_not_export(row)
            ):
                filtered_invoices.append(row)

        return filtered_invoices

    def get_cdnur_invoices(self, invoices):
        filtered_invoices = []

        for row in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(row)
                and self.is_cn_dn(row)
                and not self.has_gstin_and_is_not_export(row)
                and (self.is_export(row) or self.is_b2cl_cn_dn(row))
            ):
                filtered_invoices.append(row)

        return filtered_invoices


class GSTR1Invoices(GSTR1Sections):
    def assign_invoice_category(self, invoices):
        for row in invoices:
            if not self.is_cn_dn(row):
                if self.has_gstin_and_is_not_export(row):
                    row.invoice_category = "B2B"
                    continue

                if self.is_export(row):
                    row.invoice_category = "EXP"
                    continue

                if self.is_b2cl_invoice(row):
                    row.invoice_category = "B2CL"
                    continue

                row.invoice_category = "B2CS"
            else:
                if self.has_gstin_and_is_not_export(row):
                    row.invoice_category = "CDNR"
                    continue

                if self.is_export(row) or self.is_b2cl_cn_dn(row):
                    row.invoice_category = "CDNUR"
                    continue

                row.invoice_category = "B2CS"
        return invoices

    def get_filtered_invoices(self, invoices, invoice_category=None):
        if not invoice_category:
            return invoices

        if invoice_category == "Nil-Rated":
            return self.get_nil_rated_invoices(invoices)

        if invoice_category == "Exempted":
            return self.get_exempted_invoices(invoices)

        if invoice_category == "Non-GST":
            return self.get_non_gst_invoices(invoices)

        if invoice_category == "B2B":
            return self.get_b2b_invoices(invoices)

        if invoice_category == "Export Invoice":
            return self.get_export_invoices(invoices)

        if invoice_category == "B2C(Large)":
            return self.get_b2cl_invoices(invoices)

        if invoice_category == "B2C(Small)":
            return self.get_b2cs_invoices(invoices)

        if invoice_category == "Credit/Debit Notes Registered (CDNR)":
            return self.get_cdnr_invoices(invoices)

        if invoice_category == "Credit/Debit Notes Unregistered (CDNUR)":
            return self.get_cdnur_invoices(invoices)
