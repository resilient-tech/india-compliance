# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import json
import re

from pypika.terms import Case

import frappe
from frappe import _
from frappe.query_builder import Criterion
from frappe.query_builder.functions import Date, IfNull, Sum
from frappe.utils import cint, flt, formatdate, getdate

from india_compliance.gst_india.report.hsn_wise_summary_of_outward_supplies.hsn_wise_summary_of_outward_supplies import (
    get_columns as get_hsn_columns,
)
from india_compliance.gst_india.report.hsn_wise_summary_of_outward_supplies.hsn_wise_summary_of_outward_supplies import (
    get_hsn_data,
    get_hsn_wise_json_data,
)
from india_compliance.gst_india.utils import (
    get_escaped_name,
    get_gst_accounts_by_type,
    get_gstin_list,
    validate_invoice_number,
)
from india_compliance.gst_india.utils.exporter import ExcelExporter
from india_compliance.gst_india.utils.gstr_1 import SUPECOM, get_b2c_limit

TYPES_OF_BUSINESS = {
    "B2B": "b2b",
    "B2C Large": "b2cl",
    "B2C Small": "b2cs",
    "CDNR-REG": "cdnr",
    "CDNR-UNREG": "cdnur",
    "EXPORT": "exp",
    "Advances": "at",
    "Adjustment": "txpd",
    "NIL Rated": "nil",
    "Document Issued Summary": "doc_issue",
    "HSN": "hsn",
    "Section 14": "supeco",
}

INDEX_FOR_NIL_EXEMPT_DICT = {"Nil-Rated": 0, "Exempted": 1, "Non-GST": 2}


def execute(filters=None):
    return Gstr1Report(filters).run()


class Gstr1Report:
    def __init__(self, filters=None):
        self.filters = frappe._dict(filters or {})
        self.columns = []
        self.data = []
        self.doctype = "Sales Invoice"
        self.tax_doctype = "Sales Taxes and Charges"
        self.company_currency = frappe.get_cached_value(
            "Company", filters.get("company"), "default_currency"
        )
        self.select_columns = """
            name as invoice_number,
            customer_name,
            posting_date,
            base_grand_total,
            base_rounded_total,
            NULLIF(billing_address_gstin, '') as billing_address_gstin,
            place_of_supply,
            ecommerce_gstin,
            is_reverse_charge,
            return_against,
            is_return,
            is_debit_note,
            gst_category,
            is_export_with_gst as export_type,
            port_code,
            shipping_bill_number,
            shipping_bill_date,
            company_gstin,
            (
                CASE
                    WHEN gst_category = "Unregistered" AND NULLIF(return_against, '') is not null
                    THEN (select base_grand_total from `tabSales Invoice` ra where ra.name = si.return_against)
                END
            ) AS return_against_invoice_total
        """

    def run(self):
        self.get_columns()
        self.gst_accounts = get_gst_accounts_by_type(self.filters.company, "Output")
        self.get_data()

        return self.columns, self.data

    def get_data(self):
        if self.filters.get("type_of_business") in ("B2C Small", "B2C Large"):
            self.get_b2c_data()
        elif self.filters.get("type_of_business") in ("Advances", "Adjustment"):
            self.get_11A_11B_data()
        elif self.filters.get("type_of_business") == "NIL Rated":
            self.get_nil_rated_invoices()
        elif self.filters.get("type_of_business") == "Document Issued Summary":
            self.get_documents_issued_data()
        elif self.filters.get("type_of_business") == "HSN":
            self.data = get_hsn_data(self.filters)
        elif self.filters.get("type_of_business") == "Section 14":
            self.data = self.get_data_for_supplies_through_ecommerce_operators()
        else:
            self.get_invoice_data()
            for inv, items in self.invoice_item_details.items():
                invoice_details = self.invoices.get(inv)
                for row in items:
                    row = self.get_row_data_for_invoice(invoice_details, row)

                    if self.filters.get("type_of_business") in (
                        "CDNR-REG",
                        "CDNR-UNREG",
                    ):
                        # for Unregistered invoice, skip if B2CS
                        if self.filters.get(
                            "type_of_business"
                        ) == "CDNR-UNREG" and not self.is_b2cl_cdn(invoice_details):
                            continue

                        row["document_type"] = "C" if invoice_details.is_return else "D"

                    self.data.append(row)

    def get_nil_rated_invoices(self):
        self.get_invoice_data()
        nil_exempt_output = [
            {
                "description": "Inter-State supplies to registered persons",
                "nil_rated": 0.0,
                "exempted": 0.0,
                "non_gst": 0.0,
            },
            {
                "description": "Intra-State supplies to registered persons",
                "nil_rated": 0.0,
                "exempted": 0.0,
                "non_gst": 0.0,
            },
            {
                "description": "Inter-State supplies to unregistered persons",
                "nil_rated": 0.0,
                "exempted": 0.0,
                "non_gst": 0.0,
            },
            {
                "description": "Intra-State supplies to unregistered persons",
                "nil_rated": 0.0,
                "exempted": 0.0,
                "non_gst": 0.0,
            },
        ]

        for invoice, details in getattr(self, "nil_exempt_non_gst", {}).items():
            invoice_detail = self.invoices.get(invoice)
            if invoice_detail.get("gst_category") in ("Unregistered", "Overseas"):
                if is_inter_state(invoice_detail):
                    nil_exempt_output[2]["nil_rated"] += flt(details[0], 2)
                    nil_exempt_output[2]["exempted"] += flt(details[1], 2)
                    nil_exempt_output[2]["non_gst"] += flt(details[2], 2)
                else:
                    nil_exempt_output[3]["nil_rated"] += flt(details[0], 2)
                    nil_exempt_output[3]["exempted"] += flt(details[1], 2)
                    nil_exempt_output[3]["non_gst"] += flt(details[2], 2)
            else:
                if is_inter_state(invoice_detail):
                    nil_exempt_output[0]["nil_rated"] += flt(details[0], 2)
                    nil_exempt_output[0]["exempted"] += flt(details[1], 2)
                    nil_exempt_output[0]["non_gst"] += flt(details[2], 2)
                else:
                    nil_exempt_output[1]["nil_rated"] += flt(details[0], 2)
                    nil_exempt_output[1]["exempted"] += flt(details[1], 2)
                    nil_exempt_output[1]["non_gst"] += flt(details[2], 2)

        self.data = nil_exempt_output

    def get_b2c_data(self):
        self.get_invoice_data()
        b2c_output = {}

        for inv, items in self.invoice_item_details.items():
            invoice_details = self.invoices.get(inv)

            # for B2C Small, skip if B2CL CDN
            if self.filters.get("type_of_business") == "B2C Small" and self.is_b2cl_cdn(
                invoice_details
            ):
                continue

            for row in items:
                rate = row.get("tax_rate")
                place_of_supply = invoice_details.get("place_of_supply")
                ecommerce_gstin = invoice_details.get("ecommerce_gstin")
                invoice_number = invoice_details.get("invoice_number")

                if self.filters.get("type_of_business") == "B2C Small":
                    default_key = (rate, place_of_supply, ecommerce_gstin)

                else:
                    # B2C Large
                    default_key = (rate, place_of_supply, invoice_number)

                b2c_row = b2c_output.setdefault(
                    default_key,
                    {
                        "place_of_supply": place_of_supply,
                        "ecommerce_gstin": ecommerce_gstin,
                        "rate": rate,
                        "taxable_value": 0,
                        "cess_amount": 0,
                        "type": "",
                        "invoice_number": invoice_number,
                        "posting_date": invoice_details.get("posting_date").strftime(
                            "%d-%m-%Y"
                        ),
                        "invoice_value": flt(
                            invoice_details.get("base_grand_total"), 2
                        ),
                        "applicable_tax_rate": 0,
                    },
                )

                b2c_row["taxable_value"] += flt(row["taxable_value"])
                b2c_row["cess_amount"] += flt(row["cess_amount"])
                b2c_row["type"] = "E" if ecommerce_gstin else "OE"

        for key, value in b2c_output.items():
            self.data.append(value)

    def is_b2cl_cdn(self, invoice):
        if not (invoice.is_return or invoice.is_debit_note):
            # not CDN
            return False

        if invoice.gst_category != "Unregistered":
            return True

        if invoice.company_gstin[:2] == invoice.place_of_supply[:2]:
            # not B2CL
            return False

        grand_total = invoice.return_against_invoice_total or abs(
            invoice.base_grand_total
        )

        return grand_total > get_b2c_limit(invoice.posting_date)

    def get_row_data_for_invoice(self, invoice_details, item):
        """
        Build row for GSTR-1

        Value mapping from books to GSTR-1 Excel.
        """
        row = {}
        # For CDNR values should be positive
        item.update(
            {
                "taxable_value": abs(flt(item.get("taxable_value", 0), 2)),
                "cess_amount": abs(flt(item.get("cess_amount", 0), 2)),
            }
        )

        for fieldname in self.invoice_fields:
            if (
                self.filters.get("type_of_business") in ("CDNR-REG", "CDNR-UNREG")
                and fieldname == "invoice_value"
            ):
                row[fieldname] = flt(abs(invoice_details.base_rounded_total), 2) or flt(
                    abs(invoice_details.base_grand_total), 2
                )
            elif (
                self.filters.get("type_of_business")
                in ("CDNR-REG", "CDNR-UNREG", "B2B")
                and fieldname == "invoice_type"
            ):
                row[fieldname] = get_invoice_type_for_excel(invoice_details)
            elif fieldname == "invoice_value":
                row[fieldname] = flt(invoice_details.base_rounded_total, 2) or flt(
                    invoice_details.base_grand_total, 2
                )
            elif fieldname in ("posting_date", "shipping_bill_date"):
                row[fieldname] = formatdate(invoice_details.get(fieldname), "dd-MMM-YY")

            elif fieldname == "export_type":
                export_type = "WPAY" if invoice_details.get(fieldname) else "WOPAY"
                row[fieldname] = export_type
            else:
                row[fieldname] = invoice_details.get(fieldname)

        row.update({"rate": item.tax_rate, "applicable_tax_rate": 0, **item})

        return row

    def get_invoice_data(self):
        self.invoices = frappe._dict()
        self.invoice_item_details = frappe._dict()
        self.nil_exempt_non_gst = {}

        conditions = self.get_conditions()

        invoice_data = frappe.db.sql(
            """
            select
                {select_columns}
            from `tab{doctype}` si
            where docstatus = 1 {where_conditions}
            and is_opening = 'No'
            order by posting_date desc
            """.format(
                select_columns=self.select_columns,
                doctype=self.doctype,
                where_conditions=conditions,
            ),
            self.filters,
            as_dict=1,
        )

        for d in invoice_data:
            d.is_reverse_charge = "Y" if d.is_reverse_charge else "N"
            self.invoices.setdefault(d.invoice_number, d)

        if self.invoices:
            self.get_invoice_items()
            self.invoice_fields = [d["fieldname"] for d in self.invoice_columns]

    def get_11A_11B_data(self):
        report = GSTR11A11BData(self.filters, self.gst_accounts)
        data = report.get_data()

        for key, value in data.items():
            self.data.append(
                {
                    "place_of_supply": key[0],
                    "rate": key[1],
                    "taxable_value": value[0],
                    "cess_amount": value[1],
                    "applicable_tax_rate": 0,
                }
            )

    def get_documents_issued_data(self):
        report = GSTR1DocumentIssuedSummary(self.filters)
        data = report.get_data()

        for row in data:
            self.data.append(row)

    def get_conditions(self):
        conditions = ""

        for opts in (
            ("company", " and company=%(company)s"),
            ("from_date", " and posting_date>=%(from_date)s"),
            ("to_date", " and posting_date<=%(to_date)s"),
            ("company_address", " and company_address=%(company_address)s"),
            ("company_gstin", " and company_gstin=%(company_gstin)s"),
        ):
            if self.filters.get(opts[0]):
                conditions += opts[1]

        if self.filters.get("type_of_business") == "B2B":
            conditions += (
                "AND IFNULL(gst_category, '') not in ('Unregistered', 'Overseas') AND is_return != 1 AND"
                " is_debit_note !=1"
            )

        if self.filters.get("type_of_business") == "B2C Large":
            # get_b2c_limit hardcoded
            conditions += """
                AND ifnull(SUBSTR(place_of_supply, 1, 2),'') != ifnull(SUBSTR(company_gstin, 1, 2),'')
                AND grand_total >  (
                    CASE
                        WHEN posting_date <= '2024-07-31' THEN 250000
                        ELSE 100000
                    END
                )
                AND is_return != 1
                AND is_debit_note !=1
                AND IFNULL(gst_category, "") in ('Unregistered', 'Overseas')
                AND SUBSTR(place_of_supply, 1, 2) != '96'
            """

        elif self.filters.get("type_of_business") == "B2C Small":
            # get_b2c_limit hardcoded
            conditions += """
                AND (
                    SUBSTR(place_of_supply, 1, 2) = SUBSTR(company_gstin, 1, 2)
                    OR grand_total <= (
                        CASE
                            WHEN posting_date <= '2024-07-31' THEN 250000
                            ELSE 100000
                        END
                    )
                )
                AND IFNULL(gst_category, "") in ('Unregistered', 'Overseas')
                AND SUBSTR(place_of_supply, 1, 2) != '96'
            """

        elif self.filters.get("type_of_business") == "CDNR-REG":
            conditions += """ AND (is_return = 1 OR is_debit_note = 1) AND IFNULL(gst_category, '') not in ('Unregistered', 'Overseas')"""

        elif self.filters.get("type_of_business") == "CDNR-UNREG":
            conditions += """ AND ifnull(SUBSTR(place_of_supply, 1, 2),'') != ifnull(SUBSTR(company_gstin, 1, 2),'')
                AND (is_return = 1 OR is_debit_note = 1)
                AND IFNULL(gst_category, '') in ('Unregistered', 'Overseas')"""

        elif self.filters.get("type_of_business") == "EXPORT":
            conditions += """ AND is_return !=1 and gst_category = 'Overseas' and place_of_supply = '96-Other Countries' """

        elif self.filters.get("type_of_business") == "NIL Rated":
            conditions += """ AND IFNULL(place_of_supply, '') != '96-Other Countries' and IFNULL(gst_category, '') != 'Overseas'"""

        conditions += " AND IFNULL(billing_address_gstin, '') != company_gstin"

        return conditions

    def get_invoice_items(self):
        """
        Creates object invoice_items and nil_exempt_non_gst.

        Example invoice_items:
            {
                "INV-001": {
                    "item_code": taxable_value
                }
            }

        Example nil_exempt_non_gst:
            {
                "INV-001": [nil_rated, exempted, non_gst]
            }
        """
        sii = frappe.qb.DocType("Sales Invoice Item")
        taxable_gst_treatment = ("Taxable", "Zero-Rated")

        subquery = (
            frappe.qb.from_(sii)
            .select(
                sii.parent,
                sii.taxable_value.as_("taxable_value"),
                sii.gst_treatment,
                (sii.cgst_rate + sii.sgst_rate + sii.igst_rate).as_("tax_rate"),
                (sii.cgst_amount + sii.sgst_amount + sii.igst_amount).as_("tax_amount"),
                (sii.cess_amount + sii.cess_non_advol_amount).as_("cess_amount"),
            )
            .where(
                sii.parent.isin(list(self.invoices.keys()))
                & (sii.parenttype == "Sales Invoice")
                & (sii.docstatus == 1)
            )
        )

        if self.filters.get("type_of_business") == "NIL Rated":
            subquery = subquery.where(
                IfNull(sii.gst_treatment, "").notin(taxable_gst_treatment)
            )
        else:
            subquery = subquery.where(
                IfNull(sii.gst_treatment, "").isin(taxable_gst_treatment)
            )

        query = (
            frappe.qb.from_(subquery)
            .select(
                subquery.parent,
                Sum(subquery.taxable_value).as_("taxable_value"),
                Sum(subquery.tax_amount).as_("tax_amount"),
                Sum(subquery.cess_amount).as_("cess_amount"),
                subquery.gst_treatment,
                subquery.tax_rate,
            )
            .groupby(subquery.parent, subquery.gst_treatment, subquery.tax_rate)
        )

        items = query.run(as_dict=True)

        for d in items:
            parent = d.parent
            self.invoice_item_details.setdefault(parent, []).append(d)
            self.update_nil_exempt_non_gst(d)

    def update_nil_exempt_non_gst(self, d):
        """
        Update nil_exempt_non_gst dict with nil, exempted and non_gst values
        """
        self.nil_exempt_non_gst.setdefault(d.parent, [0.0, 0.0, 0.0])
        index = INDEX_FOR_NIL_EXEMPT_DICT.get(d.gst_treatment)

        # gst treatment is not set
        if index is None:
            return

        self.nil_exempt_non_gst[d.parent][index] += flt(d.get("taxable_value", 0), 2)

    def get_data_for_supplies_through_ecommerce_operators(self):
        si = frappe.qb.DocType("Sales Invoice")
        si_item = frappe.qb.DocType("Sales Invoice Item")
        taxes = frappe.qb.DocType("Sales Taxes and Charges")
        igst_account = get_escaped_name(self.gst_accounts.igst_account)
        cgst_account = get_escaped_name(self.gst_accounts.cgst_account)
        sgst_account = get_escaped_name(self.gst_accounts.sgst_account)
        cess_account = get_escaped_name(self.gst_accounts.cess_account)
        cess_non_advol = get_escaped_name(self.gst_accounts.cess_non_advol_account)

        # subquery to get total taxable value
        taxable_value_query = (
            frappe.qb.from_(si_item)
            .select(
                si_item.parent,
                Sum(si_item.taxable_value).as_("total_taxable_value"),
            )
            .groupby(si_item.parent)
        )

        # subquery to get total taxes
        taxes_query = (
            frappe.qb.from_(taxes)
            .select(
                taxes.parent,
                Sum(
                    Case()
                    .when(
                        taxes.account_head == igst_account,
                        taxes.tax_amount,
                    )
                    .else_(0)
                ).as_("total_igst_amount"),
                Sum(
                    Case()
                    .when(
                        taxes.account_head == cgst_account,
                        taxes.tax_amount,
                    )
                    .else_(0)
                ).as_("total_cgst_amount"),
                Sum(
                    Case()
                    .when(
                        taxes.account_head == sgst_account,
                        taxes.tax_amount,
                    )
                    .else_(0)
                ).as_("total_sgst_amount"),
                Sum(
                    Case()
                    .when(
                        taxes.account_head.isin([cess_account, cess_non_advol]),
                        taxes.tax_amount,
                    )
                    .else_(0)
                ).as_("total_cess_amount"),
            )
            .groupby(taxes.parent)
        )

        query = (
            frappe.qb.from_(si)
            .left_join(taxable_value_query)
            .on(si.name == taxable_value_query.parent)
            .left_join(taxes_query)
            .on(si.name == taxes_query.parent)
            .select(
                si.ecommerce_gstin,
                Sum(IfNull(taxable_value_query.total_taxable_value, 0)).as_(
                    "total_taxable_value"
                ),
                Sum(IfNull(taxes_query.total_igst_amount, 0)).as_("total_igst_amount"),
                Sum(IfNull(taxes_query.total_cgst_amount, 0)).as_("total_cgst_amount"),
                Sum(IfNull(taxes_query.total_sgst_amount, 0)).as_("total_sgst_amount"),
                Sum(IfNull(taxes_query.total_cess_amount, 0)).as_("total_cess_amount"),
                Case()
                .when(si.is_reverse_charge == 1, SUPECOM.US_9_5.value)
                .else_(SUPECOM.US_52.value)
                .as_("ecommerce_supply_type"),
            )
            .where(si.is_opening == "No")
            .where(si.docstatus == 1)
            .where(IfNull(si.ecommerce_gstin, "") != "")
            .where(IfNull(si.billing_address_gstin, "") != si.company_gstin)
            .where(
                Date(si.posting_date).between(
                    self.filters.from_date, self.filters.to_date
                )
            )
            .where(si.company == self.filters.company)
            .groupby(si.is_reverse_charge, si.ecommerce_gstin)
            .orderby(si.ecommerce_gstin, si.is_reverse_charge)
        )

        if self.filters.company_gstin:
            query = query.where(si.company_gstin == self.filters.company_gstin)

        return query.run(as_dict=True)

    def get_columns(self):
        self.other_columns = []
        self.tax_columns = []
        self.invoice_columns = []

        if (
            self.filters.get("type_of_business") != "NIL Rated"
            and self.filters.get("type_of_business") != "Document Issued Summary"
        ):
            self.tax_columns = [
                {
                    "fieldname": "rate",
                    "label": _("Rate"),
                    "fieldtype": "Int",
                    "width": 60,
                },
                {
                    "fieldname": "taxable_value",
                    "label": _("Taxable Value"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 150,
                },
            ]

        if self.filters.get("type_of_business") == "B2B":
            self.invoice_columns = [
                {
                    "fieldname": "billing_address_gstin",
                    "label": _("GSTIN/UIN of Recipient"),
                    "fieldtype": "Data",
                    "width": 150,
                },
                {
                    "fieldname": "customer_name",
                    "label": _("Receiver Name"),
                    "fieldtype": "Data",
                    "width": 100,
                },
                {
                    "fieldname": "invoice_number",
                    "label": _("Invoice Number"),
                    "fieldtype": "Link",
                    "options": "Sales Invoice",
                    "width": 100,
                },
                {
                    "fieldname": "posting_date",
                    "label": _("Invoice date"),
                    "fieldtype": "Data",
                    "width": 80,
                },
                {
                    "fieldname": "invoice_value",
                    "label": _("Invoice Value"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 100,
                },
                {
                    "fieldname": "place_of_supply",
                    "label": _("Place Of Supply"),
                    "fieldtype": "Data",
                    "width": 100,
                },
                {
                    "fieldname": "is_reverse_charge",
                    "label": _("Reverse Charge"),
                    "fieldtype": "Data",
                },
                {
                    "fieldname": "applicable_tax_rate",
                    "label": _("Applicable % of Tax Rate"),
                    "fieldtype": "Data",
                },
                {
                    "fieldname": "invoice_type",
                    "label": _("Invoice Type"),
                    "fieldtype": "Data",
                },
                {
                    "fieldname": "ecommerce_gstin",
                    "label": _("E-Commerce GSTIN"),
                    "fieldtype": "Data",
                    "width": 120,
                },
            ]
            self.other_columns = [
                {
                    "fieldname": "cess_amount",
                    "label": _("Cess Amount"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 100,
                }
            ]

        elif self.filters.get("type_of_business") == "B2C Large":
            self.invoice_columns = [
                {
                    "fieldname": "invoice_number",
                    "label": _("Invoice Number"),
                    "fieldtype": "Link",
                    "options": "Sales Invoice",
                    "width": 120,
                },
                {
                    "fieldname": "posting_date",
                    "label": _("Invoice date"),
                    "fieldtype": "Data",
                    "width": 100,
                },
                {
                    "fieldname": "invoice_value",
                    "label": _("Invoice Value"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 100,
                },
                {
                    "fieldname": "place_of_supply",
                    "label": _("Place Of Supply"),
                    "fieldtype": "Data",
                    "width": 120,
                },
                {
                    "fieldname": "applicable_tax_rate",
                    "label": _("Applicable % of Tax Rate"),
                    "fieldtype": "Data",
                },
            ]
            self.other_columns = [
                {
                    "fieldname": "cess_amount",
                    "label": _("Cess Amount"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 100,
                },
                {
                    "fieldname": "ecommerce_gstin",
                    "label": _("E-Commerce GSTIN"),
                    "fieldtype": "Data",
                    "width": 130,
                },
            ]
        elif self.filters.get("type_of_business") == "CDNR-REG":
            self.invoice_columns = [
                {
                    "fieldname": "billing_address_gstin",
                    "label": _("GSTIN/UIN of Recipient"),
                    "fieldtype": "Data",
                    "width": 150,
                },
                {
                    "fieldname": "customer_name",
                    "label": _("Receiver Name"),
                    "fieldtype": "Data",
                    "width": 120,
                },
                {
                    "fieldname": "invoice_number",
                    "label": _("Note Number"),
                    "fieldtype": "Link",
                    "options": "Sales Invoice",
                    "width": 120,
                },
                {
                    "fieldname": "posting_date",
                    "label": _("Note Date"),
                    "fieldtype": "Data",
                    "width": 120,
                },
                {
                    "fieldname": "document_type",
                    "label": _("Note Type"),
                    "fieldtype": "Data",
                },
                {
                    "fieldname": "place_of_supply",
                    "label": _("Place Of Supply"),
                    "fieldtype": "Data",
                    "width": 120,
                },
                {
                    "fieldname": "is_reverse_charge",
                    "label": _("Reverse Charge"),
                    "fieldtype": "Data",
                },
                {
                    "fieldname": "invoice_type",
                    "label": _("Note Supply Type"),
                    "fieldtype": "Data",
                },
                {
                    "fieldname": "invoice_value",
                    "label": _("Note Value"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 120,
                },
                {
                    "fieldname": "applicable_tax_rate",
                    "label": _("Applicable % of Tax Rate"),
                    "fieldtype": "Data",
                },
            ]
            self.other_columns = [
                {
                    "fieldname": "cess_amount",
                    "label": _("Cess Amount"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 100,
                },
            ]
        elif self.filters.get("type_of_business") == "CDNR-UNREG":
            self.invoice_columns = [
                {
                    "fieldname": "invoice_type",
                    "label": _("UR Type"),
                    "fieldtype": "Data",
                },
                {
                    "fieldname": "invoice_number",
                    "label": _("Note Number"),
                    "fieldtype": "Link",
                    "options": "Sales Invoice",
                    "width": 120,
                },
                {
                    "fieldname": "posting_date",
                    "label": _("Note Date"),
                    "fieldtype": "Data",
                    "width": 120,
                },
                {
                    "fieldname": "document_type",
                    "label": _("Note Type"),
                    "fieldtype": "Data",
                },
                {
                    "fieldname": "place_of_supply",
                    "label": _("Place Of Supply"),
                    "fieldtype": "Data",
                    "width": 120,
                },
                {
                    "fieldname": "invoice_value",
                    "label": _("Note Value"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 120,
                },
                {
                    "fieldname": "applicable_tax_rate",
                    "label": _("Applicable % of Tax Rate"),
                    "fieldtype": "Data",
                },
            ]
            self.other_columns = [
                {
                    "fieldname": "cess_amount",
                    "label": _("Cess Amount"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 100,
                },
            ]
        elif self.filters.get("type_of_business") == "B2C Small":
            self.invoice_columns = [
                {
                    "fieldname": "type",
                    "label": _("Type"),
                    "fieldtype": "Data",
                    "width": 50,
                },
                {
                    "fieldname": "place_of_supply",
                    "label": _("Place Of Supply"),
                    "fieldtype": "Data",
                    "width": 120,
                },
            ]
            self.other_columns = [
                {
                    "fieldname": "cess_amount",
                    "label": _("Cess Amount"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 100,
                },
                {
                    "fieldname": "ecommerce_gstin",
                    "label": _("E-Commerce GSTIN"),
                    "fieldtype": "Data",
                    "width": 130,
                },
            ]
            self.tax_columns.insert(
                1,
                {
                    "fieldname": "applicable_tax_rate",
                    "label": _("Applicable % of Tax Rate"),
                    "fieldtype": "Data",
                },
            )
        elif self.filters.get("type_of_business") == "EXPORT":
            self.invoice_columns = [
                {
                    "fieldname": "export_type",
                    "label": _("Export Type"),
                    "fieldtype": "Data",
                    "width": 120,
                },
                {
                    "fieldname": "invoice_number",
                    "label": _("Invoice Number"),
                    "fieldtype": "Link",
                    "options": "Sales Invoice",
                    "width": 120,
                },
                {
                    "fieldname": "posting_date",
                    "label": _("Invoice date"),
                    "fieldtype": "Data",
                    "width": 120,
                },
                {
                    "fieldname": "invoice_value",
                    "label": _("Invoice Value"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 120,
                },
                {
                    "fieldname": "port_code",
                    "label": _("Port Code"),
                    "fieldtype": "Data",
                    "width": 120,
                },
                {
                    "fieldname": "shipping_bill_number",
                    "label": _("Shipping Bill Number"),
                    "fieldtype": "Data",
                    "width": 120,
                },
                {
                    "fieldname": "shipping_bill_date",
                    "label": _("Shipping Bill Date"),
                    "fieldtype": "Data",
                    "width": 120,
                },
            ]
            self.other_columns = [
                {
                    "fieldname": "cess_amount",
                    "label": _("Cess Amount"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 130,
                }
            ]
        elif self.filters.get("type_of_business") == "Advances":
            self.columns = [
                {
                    "fieldname": "place_of_supply",
                    "label": _("Place Of Supply"),
                    "fieldtype": "Data",
                    "width": 180,
                },
                {
                    "fieldname": "rate",
                    "label": _("Rate"),
                    "fieldtype": "Int",
                    "width": 60,
                },
                {
                    "fieldname": "applicable_tax_rate",
                    "label": _("Applicable % of Tax Rate"),
                    "fieldtype": "Data",
                },
                {
                    "fieldname": "taxable_value",
                    "label": _("Gross Advance Recieved"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 150,
                },
                {
                    "fieldname": "cess_amount",
                    "label": _("Cess Amount"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 130,
                },
            ]
            return
        elif self.filters.get("type_of_business") == "Adjustment":
            self.columns = [
                {
                    "fieldname": "place_of_supply",
                    "label": _("Place Of Supply"),
                    "fieldtype": "Data",
                    "width": 180,
                },
                {
                    "fieldname": "rate",
                    "label": _("Rate"),
                    "fieldtype": "Int",
                    "width": 60,
                },
                {
                    "fieldname": "applicable_tax_rate",
                    "label": _("Applicable % of Tax Rate"),
                    "fieldtype": "Data",
                },
                {
                    "fieldname": "taxable_value",
                    "label": _("Gross Advance Adjusted"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 150,
                },
                {
                    "fieldname": "cess_amount",
                    "label": _("Cess Amount"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 130,
                },
            ]
            return
        elif self.filters.get("type_of_business") == "NIL Rated":
            self.invoice_columns = [
                {
                    "fieldname": "description",
                    "label": _("Description"),
                    "fieldtype": "Data",
                    "width": 420,
                },
                {
                    "fieldname": "nil_rated",
                    "label": _("Nil Rated Supplies"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 200,
                },
                {
                    "fieldname": "exempted",
                    "label": _("Exempted(other than nil rated/non GST supply)"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 350,
                },
                {
                    "fieldname": "non_gst",
                    "label": _("Non-GST Supplies"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 200,
                },
            ]
        elif self.filters.get("type_of_business") == "Document Issued Summary":
            self.other_columns = [
                {
                    "fieldname": "nature_of_document",
                    "label": _("Nature of Document"),
                    "fieldtype": "Data",
                    "width": 300,
                },
                {
                    "fieldname": "from_serial_no",
                    "label": _("Sr. No. From"),
                    "fieldtype": "Data",
                    "width": 160,
                },
                {
                    "fieldname": "to_serial_no",
                    "label": _("Sr. No. To"),
                    "fieldtype": "Data",
                    "width": 160,
                },
                {
                    "fieldname": "total_issued",
                    "label": _("Total Number"),
                    "fieldtype": "Int",
                    "width": 150,
                },
                {
                    "fieldname": "total_draft",
                    "label": _("Draft"),
                    "fieldtype": "Int",
                    "width": 160,
                },
                {
                    "fieldname": "cancelled",
                    "label": _("Cancelled"),
                    "fieldtype": "Int",
                    "width": 160,
                },
            ]
        elif self.filters.get("type_of_business") == "HSN":
            self.columns = get_hsn_columns(self.filters)
            return
        elif self.filters.get("type_of_business") == "Section 14":
            self.columns = self.get_section_14_columns()
            return

        self.columns = self.invoice_columns + self.tax_columns + self.other_columns

    def get_section_14_columns(self):
        return [
            {
                "fieldname": "ecommerce_gstin",
                "label": _("GSTIN of E-Commerce Operator"),
                "fieldtype": "Data",
                "width": 180,
            },
            {
                "fieldname": "total_taxable_value",
                "label": _("Net value of supplies"),
                "fieldtype": "Currency",
                "options": self.company_currency,
                "width": 120,
            },
            {
                "fieldname": "total_igst_amount",
                "label": _("Integrated tax"),
                "fieldtype": "Currency",
                "options": self.company_currency,
                "width": 120,
            },
            {
                "fieldname": "total_cgst_amount",
                "label": _("Central tax"),
                "fieldtype": "Currency",
                "options": self.company_currency,
                "width": 120,
            },
            {
                "fieldname": "total_sgst_amount",
                "label": _("State/UT tax"),
                "fieldtype": "Currency",
                "options": self.company_currency,
                "width": 120,
            },
            {
                "fieldname": "total_cess_amount",
                "label": _("Cess"),
                "fieldtype": "Currency",
                "options": self.company_currency,
                "width": 120,
            },
            {
                "fieldname": "ecommerce_supply_type",
                "label": _("Nature of Supply"),
                "fieldtype": "Data",
                "width": 180,
            },
        ]


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
            Case 1: When the difference between the serial numbers in the document names is a multiple of 10. For example, 'SINV-00010-2023' and 'SINV-00020-2023'.
            Case 2: When the serial numbers are identical, but the months differ. For example, 'SINV-01-2023-001' and 'SINV-02-2023-001'.

            Above cases are false positives and will be considered as same naming series although they are not.
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
            "Excluded from Report (Has Non GST Item)": [],
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
            elif doc.gst_treatment == "Non-GST":
                nature_of_document["Excluded from Report (Has Non GST Item)"].append(
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


@frappe.whitelist()
def get_gstr1_json(filters, data=None):
    frappe.has_permission("GL Entry", throw=True)

    report_dict = set_gst_defaults(filters)
    filters = json.loads(filters)

    filename = ["gstr-1"]
    gstin = report_dict["gstin"]
    report_types = TYPES_OF_BUSINESS

    data_dict = {}
    if data:
        type_of_business = filters.get("type_of_business")
        filename.append(frappe.scrub(type_of_business))

        report_types = {type_of_business: TYPES_OF_BUSINESS[type_of_business]}
        data_dict.setdefault(type_of_business, json.loads(data))

    filename.extend([gstin, report_dict["fp"]])

    for type_of_business, abbr in report_types.items():
        filters["type_of_business"] = type_of_business

        report_data = data_dict.get(type_of_business) or format_data_to_dict(
            execute(filters)
        )
        report_data = get_json(type_of_business, gstin, report_data, filters)

        if not report_data:
            continue

        report_dict[abbr] = report_data

    return {
        "file_name": "_".join(filename) + ".json",
        "data": report_dict,
    }


def get_json(type_of_business, gstin, data, filters):
    if data and list(data[-1].values())[0] == "Total":
        data = data[:-1]

    res = {}
    if type_of_business == "B2B":
        for item in data:
            res.setdefault(item["billing_address_gstin"], {}).setdefault(
                item["invoice_number"], []
            ).append(item)

        return get_b2b_json(res, gstin)

    if type_of_business == "B2C Large":
        for item in data:
            res.setdefault(item["place_of_supply"], []).append(item)

        return get_b2cl_json(res, gstin)

    if type_of_business == "B2C Small":
        return get_b2cs_json(data, gstin)

    if type_of_business == "EXPORT":
        for item in data:
            res.setdefault(item["export_type"], {}).setdefault(
                item["invoice_number"], []
            ).append(item)

        return get_export_json(res)

    if type_of_business == "CDNR-REG":
        for item in data:
            res.setdefault(item["billing_address_gstin"], {}).setdefault(
                item["invoice_number"], []
            ).append(item)

        return get_cdnr_reg_json(res, gstin)

    if type_of_business == "CDNR-UNREG":
        for item in data:
            res.setdefault(item["invoice_number"], []).append(item)

        return get_cdnr_unreg_json(res, gstin)

    if type_of_business in ("Advances", "Adjustment"):
        for item in data:
            if not item.get("place_of_supply"):
                frappe.throw(
                    _(
                        """{0} not entered in some entries.
                        Please update and try again"""
                    ).format(frappe.bold("Place Of Supply"))
                )

            res.setdefault(item["place_of_supply"], []).append(item)

        return get_advances_json(res, gstin)

    if type_of_business == "NIL Rated":
        return get_exempted_json(data)

    if type_of_business == "Document Issued Summary":
        return get_document_issued_summary_json(data)

    if type_of_business == "HSN":
        return get_hsn_wise_json_data(data, filters)

    if type_of_business == "Section 14":
        res.setdefault("superco", {})
        return get_section_14_json(res, data)


def set_gst_defaults(filters):
    if isinstance(filters, str):
        filters = json.loads(filters)

    gstin = filters.get("company_gstin") or get_company_gstin_number(
        filters.get("company"), filters.get("company_address")
    )

    fp = "%02d%s" % (
        getdate(filters["to_date"]).month,
        getdate(filters["to_date"]).year,
    )

    gst_json = {"version": "GST3.0.4", "hash": "hash", "gstin": gstin, "fp": fp}
    return gst_json


def format_data_to_dict(data):
    data_rows = data[1]

    if not data_rows:
        return []

    if isinstance(data_rows[0], dict):
        return data_rows

    columns = [column["fieldname"] for column in data[0]]
    report_data = [dict(zip(columns, row)) for row in data_rows]
    return report_data


def get_b2b_json(res, gstin):
    out = []
    for gst_in in res:
        b2b_item, inv = {"ctin": gst_in, "inv": []}, []
        if not gst_in:
            continue

        for number, invoice in res[gst_in].items():
            if not invoice[0]["place_of_supply"]:
                frappe.throw(
                    _(
                        """{0} not entered in Invoice {1}.
                    Please update and try again"""
                    ).format(
                        frappe.bold("Place Of Supply"),
                        frappe.bold(invoice[0]["invoice_number"]),
                    )
                )

            inv_item = get_basic_invoice_detail(invoice[0])
            inv_item["pos"] = "%02d" % int(invoice[0]["place_of_supply"].split("-")[0])
            inv_item["rchrg"] = invoice[0]["is_reverse_charge"]
            inv_item["inv_typ"] = get_invoice_type(invoice[0])

            if inv_item["pos"] == "00":
                continue
            inv_item["itms"] = []

            for item in invoice:
                inv_item["itms"].append(get_rate_and_tax_details(item, gstin))

            inv.append(inv_item)

        if not inv:
            continue
        b2b_item["inv"] = inv
        out.append(b2b_item)

    return out


def get_b2cs_json(data, gstin):
    company_state_number = gstin[0:2]

    out = []
    for d in data:
        if not d.get("place_of_supply"):
            frappe.throw(
                _(
                    """{0} not entered in some invoices.
                Please update and try again"""
                ).format(frappe.bold("Place Of Supply"))
            )

        pos = d.get("place_of_supply").split("-")[0]
        tax_details = {}

        rate = d.get("rate", 0)
        tax = flt((d["taxable_value"] * rate) / 100.0, 2)

        if company_state_number == pos:
            tax_details.update({"camt": flt(tax / 2.0, 2), "samt": flt(tax / 2.0, 2)})
        else:
            tax_details.update({"iamt": tax})

        inv = {
            "sply_ty": "INTRA" if company_state_number == pos else "INTER",
            "pos": pos,
            "typ": d.get("type"),
            "txval": flt(d.get("taxable_value"), 2),
            "rt": rate,
            "iamt": flt(tax_details.get("iamt"), 2),
            "camt": flt(tax_details.get("camt"), 2),
            "samt": flt(tax_details.get("samt"), 2),
            "csamt": flt(d.get("cess_amount"), 2),
        }

        if d.get("type") == "E" and d.get("ecommerce_gstin"):
            inv.update({"etin": d.get("ecommerce_gstin")})

        out.append(inv)

    return out


def get_advances_json(data, gstin):
    company_state_number = gstin[0:2]
    out = []
    for place_of_supply, items in data.items():
        pos = place_of_supply.split("-")[0]
        supply_type = "INTRA" if company_state_number == pos else "INTER"

        row = {"pos": pos, "itms": [], "sply_ty": supply_type}

        for item in items:
            itms = {
                "rt": item["rate"],
                "ad_amount": flt(item.get("taxable_value"), 2),
                "csamt": flt(item.get("cess_amount"), 2),
            }

            tax_amount = (itms["ad_amount"] * itms["rt"]) / 100
            if supply_type == "INTRA":
                itms.update(
                    {
                        "samt": flt(tax_amount / 2, 2),
                        "camt": flt(tax_amount / 2, 2),
                    }
                )
            else:
                itms["iamt"] = flt(tax_amount, 2)

            row["itms"].append(itms)
        out.append(row)

    return out


def get_b2cl_json(res, gstin):
    out = []
    for pos in res:
        if not pos:
            frappe.throw(
                _(
                    """{0} not entered in some invoices.
                Please update and try again"""
                ).format(frappe.bold("Place Of Supply"))
            )

        b2cl_item, inv = {"pos": "%02d" % int(pos.split("-")[0]), "inv": []}, []

        for row in res[pos]:
            inv_item = get_basic_invoice_detail(row)
            if row.get("sale_from_bonded_wh"):
                inv_item["inv_typ"] = "CBW"

            inv_item["itms"] = [get_rate_and_tax_details(row, gstin)]

            inv.append(inv_item)

        b2cl_item["inv"] = inv
        out.append(b2cl_item)

    return out


def get_export_json(res):
    out = []

    for export_type, invoice_wise_items in res.items():
        export_type_invoices = []

        for items in invoice_wise_items.values():
            invoice = get_basic_invoice_detail(items[0])
            invoice.update(get_shipping_bill_details(items[0]))
            invoice_items = invoice.setdefault("itms", [])

            for item in items:
                invoice_items.append(
                    {
                        "txval": flt(item["taxable_value"], 2),
                        "rt": flt(item["rate"]),
                        "iamt": (
                            flt((item["taxable_value"] * flt(item["rate"])) / 100.0, 2)
                            if export_type == "WPAY"
                            else 0
                        ),
                        "csamt": flt(item.get("cess_amount"), 2) or 0,
                    }
                )

            export_type_invoices.append(invoice)

        out.append({"exp_typ": export_type, "inv": export_type_invoices})

    return out


def get_cdnr_reg_json(res, gstin):
    out = []

    for gst_in in res:
        cdnr_item, inv = {"ctin": gst_in, "nt": []}, []
        if not gst_in:
            continue

        for number, invoice in res[gst_in].items():
            if not invoice[0]["place_of_supply"]:
                frappe.throw(
                    _(
                        """{0} not entered in Invoice {1}.
                    Please update and try again"""
                    ).format(
                        frappe.bold("Place Of Supply"),
                        frappe.bold(invoice[0]["invoice_number"]),
                    )
                )

            inv_item = {
                "nt_num": invoice[0]["invoice_number"],
                "nt_dt": getdate(invoice[0]["posting_date"]).strftime("%d-%m-%Y"),
                "val": abs(flt(invoice[0]["invoice_value"], 2)),
                "ntty": invoice[0]["document_type"],
                "pos": "%02d" % int(invoice[0]["place_of_supply"].split("-")[0]),
                "rchrg": invoice[0]["is_reverse_charge"],
                "inv_typ": get_invoice_type(invoice[0]),
            }

            inv_item["itms"] = []
            for item in invoice:
                inv_item["itms"].append(get_rate_and_tax_details(item, gstin))

            inv.append(inv_item)

        if not inv:
            continue
        cdnr_item["nt"] = inv
        out.append(cdnr_item)

    return out


def get_cdnr_unreg_json(res, gstin):
    out = []

    for invoice, items in res.items():
        inv_item = {
            "nt_num": items[0]["invoice_number"],
            "nt_dt": getdate(items[0]["posting_date"]).strftime("%d-%m-%Y"),
            "val": abs(flt(items[0]["invoice_value"], 2)),
            "ntty": items[0]["document_type"],
            "pos": "%02d" % int(items[0]["place_of_supply"].split("-")[0]),
            "typ": get_invoice_type(items[0]),
        }

        inv_item["itms"] = []
        for item in items:
            inv_item["itms"].append(get_rate_and_tax_details(item, gstin))

        out.append(inv_item)

    return out


def get_exempted_json(data):
    out = {
        "inv": [
            {"sply_ty": "INTRB2B", "nil_amt": 0, "expt_amt": 0, "ngsup_amt": 0},
            {"sply_ty": "INTRAB2B", "nil_amt": 0, "expt_amt": 0, "ngsup_amt": 0},
            {"sply_ty": "INTRB2C", "nil_amt": 0, "expt_amt": 0, "ngsup_amt": 0},
            {"sply_ty": "INTRAB2C", "nil_amt": 0, "expt_amt": 0, "ngsup_amt": 0},
        ]
    }

    for i, v in enumerate(data):
        if data[i].get("nil_rated"):
            out["inv"][i]["nil_amt"] = flt(data[i]["nil_rated"], 2)

        if data[i].get("exempted"):
            out["inv"][i]["expt_amt"] = flt(data[i]["exempted"], 2)

        if data[i].get("non_gst"):
            out["inv"][i]["ngsup_amt"] = flt(data[i]["non_gst"], 2)

    return out


def get_document_issued_summary_json(data):
    document_types = {
        "Invoices for outward supply": 1,
        "Debit Note": 4,
        "Credit Note": 5,
        "Invoices for inward supply from unregistered person": 2,
    }

    document_lists = {document_type: [] for document_type in document_types}

    for row in data:
        if row["nature_of_document"] not in document_types:
            continue

        document_lists[row["nature_of_document"]].append(
            {
                "num": len(document_lists[row["nature_of_document"]]) + 1,
                "to": row["to_serial_no"],
                "from": row["from_serial_no"],
                "totnum": row["total_issued"],
                "cancel": row["cancelled"] + row["total_draft"],
                "net_issue": row["total_submitted"],
            }
        )

    doc_det = []

    for document_type in document_lists:
        doc_det.append(
            {
                "doc_num": document_types[document_type],
                "doc_typ": document_type,
                "docs": document_lists[document_type],
            }
        )

    return {"doc_det": doc_det}


def get_section_14_json(res, data):
    out = res["superco"]
    for item in data:
        key = (
            "clttx" if item["ecommerce_supply_type"] == SUPECOM.US_52.value else "paytx"
        )
        out.setdefault(key, []).append(
            {
                "etin": item["ecommerce_gstin"],
                "suppval": item["total_taxable_value"],
                "igst": item["total_igst_amount"],
                "cgst": item["total_cgst_amount"],
                "sgst": item["total_sgst_amount"],
                "cess": item["total_cess_amount"],
            }
        )

    return out


def get_invoice_type(row):
    invoice_type = row.get("invoice_type")
    return (
        {
            "Regular B2B": "R",
            "Deemed Exp": "DE",
            "SEZ supplies with payment": "SEWP",
            "SEZ supplies without payment": "SEWOP",
            "B2CL": "B2CL",
            "EXPWP": "EXPWP",
            "EXPWOP": "EXPWOP",
        }
    ).get(invoice_type)


def get_invoice_type_for_excel(row):
    gst_category = row.get("gst_category")

    if gst_category == "SEZ":
        return (
            "SEZ supplies with payment"
            if row.get("export_type")
            else "SEZ supplies without payment"
        )

    if gst_category == "Overseas":
        return "EXPWP" if row.get("export_type") else "EXPWOP"

    return (
        {
            "Deemed Export": "Deemed Exp",
            "Registered Regular": "Regular B2B",
            "Registered Composition": "Regular B2B",
            "Tax Deductor": "Regular B2B",
            "UIN Holders": "Regular B2B",
            "Unregistered": "B2CL",
            "Tax Collector": "Regular B2B",
            "Input Service Distributor": "Regular B2B",
        }
    ).get(gst_category)


def get_basic_invoice_detail(row):
    return {
        "inum": row["invoice_number"],
        "idt": getdate(row["posting_date"]).strftime("%d-%m-%Y"),
        "val": flt(row["invoice_value"], 2),
    }


def get_shipping_bill_details(row):
    if not row.get("shipping_bill_number"):
        return {}

    return {
        "sbpcode": row["port_code"],
        "sbnum": row["shipping_bill_number"],
        "sbdt": getdate(row["shipping_bill_date"]).strftime("%d-%m-%Y"),
    }


def get_rate_and_tax_details(row, gstin):
    itm_det = {
        "txval": flt(row["taxable_value"], 2),
        "rt": row["rate"],
        "csamt": (flt(row.get("cess_amount"), 2) or 0),
    }

    # calculate rate
    num = 1 if not row["rate"] else "%d%02d" % (row["rate"], 1)
    rate = row.get("rate") or 0

    # calculate tax amount added
    tax = flt((row["taxable_value"] * rate) / 100.0, 2)
    if (
        row.get("billing_address_gstin")
        and gstin[0:2] == row["billing_address_gstin"][0:2]
    ):
        itm_det.update({"camt": flt(tax / 2.0, 2), "samt": flt(tax / 2.0, 2)})
    else:
        itm_det.update({"iamt": tax})

    return {"num": int(num), "itm_det": itm_det}


def get_company_gstin_number(company, address=None, all_gstins=False):
    gstin = ""
    if address:
        gstin = frappe.db.get_value("Address", address, "gstin")

    if not gstin:
        gstin = get_gstin_list(company)
        if gstin and not all_gstins:
            gstin = gstin[0]

    if not gstin:
        address = frappe.bold(address) if address else ""
        frappe.throw(
            _("Please set valid GSTIN No. in Company Address {} for company {}").format(
                address, frappe.bold(company)
            )
        )

    return gstin


@frappe.whitelist()
def download_json_file():
    """download json content in a file"""
    data = frappe._dict(frappe.local.form_dict)
    report_data = json.loads(data["data"])

    frappe.response["filename"] = (
        frappe.scrub(
            "{0} {1} {2} {3}".format(
                data["report_name"],
                data["report_type"],
                report_data["gstin"],
                report_data["fp"],
            )
        )
        + ".json"
    )
    frappe.response["filecontent"] = data["data"]
    frappe.response["content_type"] = "application/json"
    frappe.response["type"] = "download"


def is_inter_state(invoice_detail):
    if invoice_detail.place_of_supply.split("-")[0] != invoice_detail.company_gstin[:2]:
        return True
    else:
        return False


@frappe.whitelist()
def get_gstr1_excel(filters, data=None, columns=None):
    frappe.has_permission("GL Entry", throw=True)

    report_dict = set_gst_defaults(filters)
    filters = json.loads(filters)

    filename = ["GSTR-1"]
    gstin = report_dict["gstin"]
    report_types = TYPES_OF_BUSINESS

    excel = ExcelExporter()
    excel.remove_sheet("Sheet")

    if isinstance(data, str):
        type_of_business = filters.get("type_of_business")
        filename.append(type_of_business)

        data = json.loads(data)
        data = data[:-1] if data else data
        headers = json.loads(columns) if columns else []

        if not data:
            # Retrieve report data if data is empty
            report_data = execute(filters)
            headers = report_data[0] or []
            data = format_data_to_dict(report_data)

        if type_of_business == "Document Issued Summary":
            format_doc_issued_excel_data(headers, data)

        if type_of_business == "HSN" and filters.get("bifurcate_hsn"):
            create_hsn_excel_sheet(excel, headers, data)
        else:
            create_excel_sheet(excel, type_of_business, headers, data)

    else:
        for type_of_business in report_types:
            filters["type_of_business"] = type_of_business
            report_data = execute(filters)

            headers = report_data[0] or []
            data = format_data_to_dict(report_data)

            if type_of_business == "Document Issued Summary":
                format_doc_issued_excel_data(headers, data)

            if type_of_business == "HSN" and filters.get("bifurcate_hsn"):
                create_hsn_excel_sheet(excel, headers, data)
                continue

            create_excel_sheet(excel, type_of_business, headers, data)

    filename.extend([gstin, report_dict["fp"]])
    excel.export("_".join(filename))


def format_doc_issued_excel_data(headers, data):
    # add total_draft count to cancelled count
    for doc in data:
        doc["cancelled"] += doc.get("total_draft", 0)

    # remove total_draft column from headers
    total_draft_idx = next(
        (
            idx
            for idx, header in enumerate(headers)
            if header["fieldname"] == "total_draft"
        ),
        None,
    )

    if total_draft_idx is not None:
        headers.pop(total_draft_idx)


def create_hsn_excel_sheet(excel, headers, data):
    b2b_data = []
    b2c_data = []
    for row in data:
        if row.get("invoice_type") == "B2B":
            b2b_data.append(row)
        else:
            b2c_data.append(row)

    if b2b_data:
        create_excel_sheet(excel, "HSN - B2B", headers, b2b_data)

    if b2c_data:
        create_excel_sheet(excel, "HSN - B2C", headers, b2c_data)


def create_excel_sheet(excel, sheet_name, headers, data):
    excel.create_sheet(
        sheet_name=sheet_name, headers=headers, data=data, add_totals=False
    )
