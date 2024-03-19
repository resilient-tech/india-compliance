# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import getdate


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


def get_invoices_for_hsn_wise_summary(filters):
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
            si.gst_category,
            si_item.gst_treatment,
            (si_item.cgst_rate + si_item.sgst_rate + si_item.igst_rate).as_("gst_rate"),
        )
        .where(si.docstatus == 1)
        .where(si.is_opening != "Yes")
    )

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

    def is_nil_rated(self, row):
        return row.gst_treatment == "Nil-Rated"

    def is_exempted(self, row):
        return row.gst_treatment == "Exempted"

    def is_non_gst(self, row):
        return row.gst_treatment == "Non-GST"

    def is_nil_rated_exempted_or_non_gst(self, row):
        return self.is_nil_rated(row) or self.is_exempted(row) or self.is_non_gst(row)

    def is_cn_dn(self, row):
        return row.is_return or row.is_debit_note

    def has_gstin_and_is_not_export(self, row):
        return row.billing_address_gstin and row.place_of_supply != "96-Other Countries"

    def is_export(self, row):
        return row.place_of_supply == "96-Other Countries"

    def is_b2cl_cn_dn(self, row):
        return row.total > 250000 and row.company_gstin[:2] != row.place_of_supply[:2]

    def is_b2cl_invoice(self, row):
        return row.total > 250000 and row.company_gstin[:2] != row.place_of_supply[:2]

    def is_b2cs_cn_dn(self, row):
        return not self.is_b2cl_cn_dn(row)

    def is_b2cs_invoice(self, row):
        return not self.is_b2cl_invoice(row)


class GSTR1Sections(GSTR1Conditions):

    def get_nil_rated_invoices(self, invoices):
        filtered_invoices = []
        for row in invoices:
            if self.is_nil_rated(row):
                filtered_invoices.append(row)

        return filtered_invoices

    def get_exempted_invoices(self, invoices):
        filtered_invoices = []
        for row in invoices:
            if self.is_exempted(row):
                filtered_invoices.append(row)

        return filtered_invoices

    def get_non_gst_invoices(self, invoices):
        filtered_invoices = []
        for row in invoices:
            if self.is_non_gst(row):
                filtered_invoices.append(row)

        return filtered_invoices

    def get_b2b_invoices(self, invoices):
        filtered_invoices = []

        for row in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(row)
                and not self.is_cn_dn(row)
                and self.has_gstin_and_is_not_export(row)
            ):
                filtered_invoices.append(row)

        return filtered_invoices

    def get_export_invoices(self, invoices):
        filtered_invoices = []

        for row in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(row)
                and not self.is_cn_dn(row)
                and self.is_export(row)
            ):
                filtered_invoices.append(row)

        return filtered_invoices

    def get_b2cl_invoices(self, invoices):
        filtered_invoices = []

        for row in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(row)
                and not self.is_cn_dn(row)
                and not self.has_gstin_and_is_not_export(row)
                and not self.is_export(row)
                and self.is_b2cl_invoice(row)
            ):
                filtered_invoices.append(row)

        return filtered_invoices

    def get_b2cs_invoices(self, invoices):
        filtered_invoices = []

        for row in invoices:
            if (
                not self.is_nil_rated_exempted_or_non_gst(row)
                and not self.has_gstin_and_is_not_export(row)
                and not self.is_export(row)
                and (self.is_b2cs_cn_dn(row) or self.is_b2cs_invoice(row))
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

    def get_filtered_invoices(self, invoices, filter=None):
        if not filter:
            return invoices

        if filter == "Nil-Rated":
            return self.get_nil_rated_invoices(invoices)

        if filter == "Exempted":
            return self.get_exempted_invoices(invoices)

        if filter == "Non-GST":
            return self.get_non_gst_invoices(invoices)

        if filter == "B2B":
            return self.get_b2b_invoices(invoices)

        if filter == "Export Invoice":
            return self.get_export_invoices(invoices)

        if filter == "B2C(Large)":
            return self.get_b2cl_invoices(invoices)

        if filter == "B2C(Small)":
            return self.get_b2cs_invoices(invoices)

        if filter == "Credit/Debit Notes Registered (CDNR)":
            return self.get_cdnr_invoices(invoices)

        if filter == "Credit/Debit Notes Unregistered (CDNUR)":
            return self.get_cdnur_invoices(invoices)
