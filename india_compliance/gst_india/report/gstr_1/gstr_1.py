# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import json
from datetime import date

from pypika.terms import Case

import frappe
from frappe import _
from frappe.query_builder import Criterion
from frappe.query_builder.functions import Sum
from frappe.utils import flt, formatdate, getdate

from india_compliance.gst_india.utils import (
    get_gst_accounts_by_type,
    is_overseas_transaction,
)

B2C_LIMIT = 2_50_000


def execute(filters=None):
    return Gstr1Report(filters).run()


class Gstr1Report:
    def __init__(self, filters=None):
        self.filters = frappe._dict(filters or {})
        self.columns = []
        self.data = []
        self.doctype = "Sales Invoice"
        self.tax_doctype = "Sales Taxes and Charges"
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
			reason_for_issuing_document,
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
        self.get_invoice_data()

        if self.invoices:
            self.get_invoice_items()
            self.get_items_based_on_tax_rate()
            self.invoice_fields = [d["fieldname"] for d in self.invoice_columns]

        self.get_data()

        return self.columns, self.data

    def get_data(self):
        if self.filters.get("type_of_business") in ("B2C Small", "B2C Large"):
            self.get_b2c_data()
        elif self.filters.get("type_of_business") in ("Advances", "Adjustment"):
            self.get_11A_11B_data()
        elif self.filters.get("type_of_business") == "NIL Rated":
            self.get_nil_rated_invoices()
        elif self.invoices:
            for inv, items_based_on_rate in self.items_based_on_tax_rate.items():
                invoice_details = self.invoices.get(inv)
                for rate, items in items_based_on_rate.items():
                    row, taxable_value = self.get_row_data_for_invoice(
                        inv, invoice_details, rate, items
                    )

                    if self.filters.get("type_of_business") in (
                        "CDNR-REG",
                        "CDNR-UNREG",
                    ):
                        # for Unregistered invoice, skip if B2CS
                        if self.filters.get(
                            "type_of_business"
                        ) == "CDNR-UNREG" and not self.is_b2cl_cdn(invoice_details):
                            continue

                        row.append(
                            "Y"
                            if invoice_details.posting_date <= date(2017, 7, 1)
                            else "N"
                        )
                        row.append("C" if invoice_details.is_return else "D")

                    if taxable_value:
                        self.data.append(row)

    def get_nil_rated_invoices(self):
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
            if invoice_detail.get("gst_category") in (
                "Registered Regular",
                "Deemed Export",
                "SEZ",
            ):
                if is_inter_state(invoice_detail):
                    nil_exempt_output[0]["nil_rated"] += details[0]
                    nil_exempt_output[0]["exempted"] += details[1]
                    nil_exempt_output[0]["non_gst"] += details[2]
                else:
                    nil_exempt_output[1]["nil_rated"] += details[0]
                    nil_exempt_output[1]["exempted"] += details[1]
                    nil_exempt_output[1]["non_gst"] += details[2]
            else:
                if is_inter_state(invoice_detail):
                    nil_exempt_output[2]["nil_rated"] += details[0]
                    nil_exempt_output[2]["exempted"] += details[1]
                    nil_exempt_output[2]["non_gst"] += details[2]
                else:
                    nil_exempt_output[3]["nil_rated"] += details[0]
                    nil_exempt_output[3]["exempted"] += details[1]
                    nil_exempt_output[3]["non_gst"] += details[2]

        self.data = nil_exempt_output

    def get_b2c_data(self):
        b2c_output = {}

        if self.invoices:
            for inv, items_based_on_rate in self.items_based_on_tax_rate.items():
                invoice_details = self.invoices.get(inv)

                # for B2C Small, skip if B2CL CDN
                if self.filters.get(
                    "type_of_business"
                ) == "B2C Small" and self.is_b2cl_cdn(invoice_details):
                    continue

                for rate, items in items_based_on_rate.items():
                    place_of_supply = invoice_details.get("place_of_supply")
                    ecommerce_gstin = invoice_details.get("ecommerce_gstin")
                    invoice_number = invoice_details.get("invoice_number")

                    if self.filters.get("type_of_business") == "B2C Small":
                        default_key = (rate, place_of_supply, ecommerce_gstin)

                    else:
                        # B2C Large
                        default_key = (rate, place_of_supply, invoice_number)

                    b2c_output.setdefault(
                        default_key,
                        {
                            "place_of_supply": place_of_supply,
                            "ecommerce_gstin": ecommerce_gstin,
                            "rate": rate,
                            "taxable_value": 0,
                            "cess_amount": 0,
                            "type": "",
                            "invoice_number": invoice_number,
                            "posting_date": invoice_details.get("posting_date"),
                            "invoice_value": invoice_details.get("base_grand_total"),
                        },
                    )

                    row = b2c_output.get(default_key)
                    row["taxable_value"] += sum(
                        [
                            net_amount
                            for item_code, net_amount in self.invoice_items.get(
                                inv
                            ).items()
                            if item_code in items
                        ]
                    )
                    row["cess_amount"] += sum(
                        [
                            cess
                            for item_code, cess in self.invoice_cess.get(
                                inv, {}
                            ).items()
                            if item_code in items
                        ]
                    )
                    row["type"] = "E" if ecommerce_gstin else "OE"

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
        return grand_total > B2C_LIMIT

    def get_row_data_for_invoice(self, invoice, invoice_details, tax_rate, items):
        row = []
        for fieldname in self.invoice_fields:
            if (
                self.filters.get("type_of_business") in ("CDNR-REG", "CDNR-UNREG")
                and fieldname == "invoice_value"
            ):
                row.append(
                    abs(invoice_details.base_rounded_total)
                    or abs(invoice_details.base_grand_total)
                )
            elif fieldname == "invoice_value":
                row.append(
                    invoice_details.base_rounded_total
                    or invoice_details.base_grand_total
                )
            elif fieldname in ("posting_date", "shipping_bill_date"):
                row.append(formatdate(invoice_details.get(fieldname), "dd-MMM-YY"))
            elif fieldname == "export_type":
                export_type = "WPAY" if invoice_details.get(fieldname) else "WOPAY"
                row.append(export_type)
            else:
                row.append(invoice_details.get(fieldname))
        taxable_value = 0
        cess_amount = 0

        for item_code, net_amount in self.invoice_items.get(invoice).items():
            if item_code in items:
                taxable_value += abs(net_amount)
                cess_amount += self.invoice_cess.get(invoice, {}).get(item_code, 0.0)

        row += [tax_rate or 0, taxable_value]

        for column in self.other_columns:
            if column.get("fieldname") == "cess_amount":
                row.append(cess_amount)

        return row, taxable_value

    def get_invoice_data(self):
        self.invoices = frappe._dict()
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

    def get_11A_11B_data(self):
        report = GSTR11A11BData(self.filters, self.gst_accounts)
        data = report.get_data()

        for key, value in data.items():
            row = [key[0], key[1], value[0], value[1]]
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
            conditions += """ AND ifnull(SUBSTR(place_of_supply, 1, 2),'') != ifnull(SUBSTR(company_gstin, 1, 2),'')
				AND grand_total > {0} AND is_return != 1 AND is_debit_note !=1
                AND IFNULL(gst_category, "") in ('Unregistered', 'Overseas')
                AND SUBSTR(place_of_supply, 1, 2) != '96'""".format(
                B2C_LIMIT
            )

        elif self.filters.get("type_of_business") == "B2C Small":
            conditions += """ AND (
				SUBSTR(place_of_supply, 1, 2) = SUBSTR(company_gstin, 1, 2)
					OR grand_total <= {0}) AND IFNULL(gst_category, "") in ('Unregistered', 'Overseas')
                    AND SUBSTR(place_of_supply, 1, 2) != '96' """.format(
                B2C_LIMIT
            )

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
        self.invoice_items = frappe._dict()
        self.nil_exempt_non_gst = {}

        items = frappe.db.sql(
            """
			select item_code, item_name, parent, taxable_value, item_tax_rate, is_nil_exempt,
			is_non_gst from `tab%s Item`
			where parent in (%s)
		"""
            % (self.doctype, ", ".join(["%s"] * len(self.invoices))),
            tuple(self.invoices),
            as_dict=1,
        )

        for d in items:
            d.item_code = d.item_code or d.item_name
            self.invoice_items.setdefault(d.parent, {}).setdefault(d.item_code, 0.0)
            self.invoice_items[d.parent][d.item_code] += d.get("taxable_value", 0)

            if d.is_nil_exempt:
                self.nil_exempt_non_gst.setdefault(d.parent, [0.0, 0.0, 0.0])
                if d.item_tax_rate:
                    self.nil_exempt_non_gst[d.parent][0] += d.get("taxable_value", 0)
                else:
                    self.nil_exempt_non_gst[d.parent][1] += d.get("taxable_value", 0)
            elif d.is_non_gst:
                self.nil_exempt_non_gst.setdefault(d.parent, [0.0, 0.0, 0.0])
                self.nil_exempt_non_gst[d.parent][2] += d.get("taxable_value", 0)

    def get_items_based_on_tax_rate(self):
        tax_details = frappe.db.sql(
            """
			select
				parent, account_head, item_wise_tax_detail
			from `tab%s`
			where
				parenttype = %s and docstatus = 1
				and parent in (%s)
			order by account_head
		"""
            % (self.tax_doctype, "%s", ", ".join(["%s"] * len(self.invoices.keys()))),
            tuple([self.doctype] + list(self.invoices.keys())),
        )

        self.items_based_on_tax_rate = {}
        self.invoice_cess = frappe._dict()

        unidentified_gst_accounts = set()
        unidentified_gst_accounts_invoice = set()
        for parent, account, item_wise_tax_detail in tax_details:
            if not item_wise_tax_detail:
                continue

            if account not in self.gst_accounts.values():
                if "gst" in account.lower():
                    unidentified_gst_accounts.add(account)
                    unidentified_gst_accounts_invoice.add(parent)

                continue

            try:
                item_wise_tax_detail = json.loads(item_wise_tax_detail)
            except ValueError:
                continue

            is_cess = account == self.gst_accounts.cess_account
            is_cgst_or_sgst = (
                account == self.gst_accounts.cgst_account
                or account == self.gst_accounts.sgst_account
            )

            for item_code, tax_amounts in item_wise_tax_detail.items():
                tax_rate = tax_amounts[0]

                if not tax_rate and parent not in self.nil_exempt_non_gst:
                    continue

                if is_cess:
                    self.invoice_cess.setdefault(parent, {})
                    self.invoice_cess[parent].setdefault(item_code, 0.0)
                    self.invoice_cess[parent][item_code] += tax_amounts[1]
                    continue

                if is_cgst_or_sgst:
                    tax_rate *= 2

                (
                    self.items_based_on_tax_rate.setdefault(parent, {})
                    .setdefault(tax_rate, set())
                    .add(item_code)
                )

        if unidentified_gst_accounts:
            frappe.msgprint(
                _("Following accounts might be selected in GST Settings:")
                + "<br>"
                + "<br>".join(unidentified_gst_accounts),
                alert=True,
            )

        # Build itemised tax for export invoices where tax table is blank
        for invoice_no, items in self.invoice_items.items():
            if (
                invoice_no in self.items_based_on_tax_rate
                or invoice_no in unidentified_gst_accounts_invoice
            ):
                continue

            invoice = self.invoices.get(invoice_no, {})
            if not invoice.get("is_export_with_gst") and is_overseas_transaction(
                "Sales Invoice", invoice.gst_category, invoice.place_of_supply
            ):
                self.items_based_on_tax_rate.setdefault(invoice_no, {}).setdefault(
                    0, []
                ).extend(items)

            # Show invoice with all items are in nil exempt and exclude non-gst
            if (
                invoice_no in self.nil_exempt_non_gst
                and self.nil_exempt_non_gst[invoice_no][2] == 0
            ):
                self.items_based_on_tax_rate.setdefault(invoice_no, {}).setdefault(
                    0, []
                ).extend(items)

    def get_columns(self):
        self.other_columns = []
        self.tax_columns = []

        if self.filters.get("type_of_business") != "NIL Rated":
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
                    "fieldname": "gst_category",
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
                    "width": 100,
                },
                {
                    "fieldname": "place_of_supply",
                    "label": _("Place Of Supply"),
                    "fieldtype": "Data",
                    "width": 120,
                },
                {
                    "fieldname": "ecommerce_gstin",
                    "label": _("E-Commerce GSTIN"),
                    "fieldtype": "Data",
                    "width": 130,
                },
            ]
            self.other_columns = [
                {
                    "fieldname": "cess_amount",
                    "label": _("Cess Amount"),
                    "fieldtype": "Currency",
                    "width": 100,
                }
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
                    "fieldname": "return_against",
                    "label": _("Invoice/Advance Receipt Number"),
                    "fieldtype": "Link",
                    "options": "Sales Invoice",
                    "width": 120,
                },
                {
                    "fieldname": "posting_date",
                    "label": _("Invoice/Advance Receipt date"),
                    "fieldtype": "Data",
                    "width": 120,
                },
                {
                    "fieldname": "invoice_number",
                    "label": _("Invoice/Advance Receipt Number"),
                    "fieldtype": "Link",
                    "options": "Sales Invoice",
                    "width": 120,
                },
                {
                    "fieldname": "is_reverse_charge",
                    "label": _("Reverse Charge"),
                    "fieldtype": "Data",
                },
                {
                    "fieldname": "export_type",
                    "label": _("Export Type"),
                    "fieldtype": "Data",
                    "hidden": 1,
                },
                {
                    "fieldname": "reason_for_issuing_document",
                    "label": _("Reason For Issuing document"),
                    "fieldtype": "Data",
                    "width": 140,
                },
                {
                    "fieldname": "place_of_supply",
                    "label": _("Place Of Supply"),
                    "fieldtype": "Data",
                    "width": 120,
                },
                {
                    "fieldname": "gst_category",
                    "label": _("GST Category"),
                    "fieldtype": "Data",
                },
                {
                    "fieldname": "invoice_value",
                    "label": _("Invoice Value"),
                    "fieldtype": "Currency",
                    "width": 120,
                },
            ]
            self.other_columns = [
                {
                    "fieldname": "cess_amount",
                    "label": _("Cess Amount"),
                    "fieldtype": "Currency",
                    "width": 100,
                },
                {
                    "fieldname": "pre_gst",
                    "label": _("PRE GST"),
                    "fieldtype": "Data",
                    "width": 80,
                },
                {
                    "fieldname": "document_type",
                    "label": _("Document Type"),
                    "fieldtype": "Data",
                    "width": 80,
                },
            ]
        elif self.filters.get("type_of_business") == "CDNR-UNREG":
            self.invoice_columns = [
                {
                    "fieldname": "customer_name",
                    "label": _("Receiver Name"),
                    "fieldtype": "Data",
                    "width": 120,
                },
                {
                    "fieldname": "return_against",
                    "label": _("Issued Against"),
                    "fieldtype": "Link",
                    "options": "Sales Invoice",
                    "width": 120,
                },
                {
                    "fieldname": "posting_date",
                    "label": _("Note Date"),
                    "fieldtype": "Date",
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
                    "fieldname": "export_type",
                    "label": _("Export Type"),
                    "fieldtype": "Data",
                    "hidden": 1,
                },
                {
                    "fieldname": "reason_for_issuing_document",
                    "label": _("Reason For Issuing document"),
                    "fieldtype": "Data",
                    "width": 140,
                },
                {
                    "fieldname": "place_of_supply",
                    "label": _("Place Of Supply"),
                    "fieldtype": "Data",
                    "width": 120,
                },
                {
                    "fieldname": "gst_category",
                    "label": _("GST Category"),
                    "fieldtype": "Data",
                },
                {
                    "fieldname": "invoice_value",
                    "label": _("Invoice Value"),
                    "fieldtype": "Currency",
                    "width": 120,
                },
            ]
            self.other_columns = [
                {
                    "fieldname": "cess_amount",
                    "label": _("Cess Amount"),
                    "fieldtype": "Currency",
                    "width": 100,
                },
                {
                    "fieldname": "pre_gst",
                    "label": _("PRE GST"),
                    "fieldtype": "Data",
                    "width": 80,
                },
                {
                    "fieldname": "document_type",
                    "label": _("Document Type"),
                    "fieldtype": "Data",
                    "width": 80,
                },
            ]
        elif self.filters.get("type_of_business") == "B2C Small":
            self.invoice_columns = [
                {
                    "fieldname": "place_of_supply",
                    "label": _("Place Of Supply"),
                    "fieldtype": "Data",
                    "width": 120,
                },
                {
                    "fieldname": "ecommerce_gstin",
                    "label": _("E-Commerce GSTIN"),
                    "fieldtype": "Data",
                    "width": 130,
                },
            ]
            self.other_columns = [
                {
                    "fieldname": "cess_amount",
                    "label": _("Cess Amount"),
                    "fieldtype": "Currency",
                    "width": 100,
                },
                {
                    "fieldname": "type",
                    "label": _("Type"),
                    "fieldtype": "Data",
                    "width": 50,
                },
            ]
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
        elif self.filters.get("type_of_business") in ("Advances", "Adjustment"):
            self.invoice_columns = [
                {
                    "fieldname": "place_of_supply",
                    "label": _("Place Of Supply"),
                    "fieldtype": "Data",
                    "width": 180,
                }
            ]

            self.other_columns = [
                {
                    "fieldname": "cess_amount",
                    "label": _("Cess Amount"),
                    "fieldtype": "Currency",
                    "width": 130,
                }
            ]
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
                    "label": _("Nil Rated"),
                    "fieldtype": "Currency",
                    "width": 200,
                },
                {
                    "fieldname": "exempted",
                    "label": _("Exempted"),
                    "fieldtype": "Currency",
                    "width": 200,
                },
                {
                    "fieldname": "non_gst",
                    "label": _("Non GST"),
                    "fieldtype": "Currency",
                    "width": 200,
                },
            ]

        self.columns = self.invoice_columns + self.tax_columns + self.other_columns


class GSTR11A11BData:
    def __init__(self, filters, gst_accounts):
        self.filters = filters

        self.pe = frappe.qb.DocType("Payment Entry")
        self.pe_ref = frappe.qb.DocType("Payment Entry Reference")
        self.gl_entry = frappe.qb.DocType("GL Entry")
        self.gst_accounts = gst_accounts

    def get_data(self):
        if self.filters.get("type_of_business") == "Advances":
            records = self.get_11A_data()

        elif self.filters.get("type_of_business") == "Adjustment":
            records = self.get_11B_data()

        return self.process_data(records, self.filters.get("type_of_business"))

    def get_11A_data(self):
        return (
            self.get_query()
            .select(self.pe.paid_amount.as_("taxable_value"))
            .groupby(self.pe.name)
            .run(as_dict=True)
        )

    def get_11B_data(self):
        query = (
            self.get_query()
            .join(self.pe_ref)
            .on(self.pe_ref.name == self.gl_entry.voucher_detail_no)
            .select(self.pe_ref.allocated_amount.as_("taxable_value"))
            .groupby(self.gl_entry.voucher_detail_no)
        )

        return query.run(as_dict=True)

    def get_query(self):
        cr_or_dr = (
            "credit" if self.filters.get("type_of_business") == "Advances" else "debit"
        )
        cr_or_dr_amount_field = getattr(
            self.gl_entry, f"{cr_or_dr}_in_account_currency"
        )

        return (
            frappe.qb.from_(self.gl_entry)
            .join(self.pe)
            .on(self.pe.name == self.gl_entry.voucher_no)
            .select(
                self.pe.place_of_supply,
                Sum(
                    Case()
                    .when(
                        self.gl_entry.account != self.gst_accounts.cess_account,
                        cr_or_dr_amount_field,
                    )
                    .else_(0)
                ).as_("tax_amount"),
                Sum(
                    Case()
                    .when(
                        self.gl_entry.account == self.gst_accounts.cess_account,
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

    def process_data(self, records, type):
        data = {}
        for entry in records:
            tax_rate = round(((entry.tax_amount / entry.taxable_value) * 100))

            data.setdefault((entry.place_of_supply, tax_rate), [0.0, 0.0])

            data[(entry.place_of_supply, tax_rate)][0] += entry.taxable_value
            data[(entry.place_of_supply, tax_rate)][1] += entry.cess_amount

        return data


@frappe.whitelist()
def get_json(filters, report_name, data):
    """
    This function does not check for permissions since it only manipulates data sent to it
    """

    filters = json.loads(filters)
    report_data = json.loads(data)
    gstin = filters.get("company_gstin") or get_company_gstin_number(
        filters.get("company"), filters.get("company_address")
    )

    fp = "%02d%s" % (
        getdate(filters["to_date"]).month,
        getdate(filters["to_date"]).year,
    )

    gst_json = {"version": "GST3.0.4", "hash": "hash", "gstin": gstin, "fp": fp}

    res = {}
    if filters["type_of_business"] == "B2B":
        for item in report_data[:-1]:
            res.setdefault(item["billing_address_gstin"], {}).setdefault(
                item["invoice_number"], []
            ).append(item)

        out = get_b2b_json(res, gstin)
        gst_json["b2b"] = out

    elif filters["type_of_business"] == "B2C Large":
        for item in report_data[:-1]:
            res.setdefault(item["place_of_supply"], []).append(item)

        out = get_b2cl_json(res, gstin)
        gst_json["b2cl"] = out

    elif filters["type_of_business"] == "B2C Small":
        out = get_b2cs_json(report_data[:-1], gstin)
        gst_json["b2cs"] = out

    elif filters["type_of_business"] == "EXPORT":
        for item in report_data[:-1]:
            res.setdefault(item["export_type"], {}).setdefault(
                item["invoice_number"], []
            ).append(item)

        out = get_export_json(res)
        gst_json["exp"] = out
    elif filters["type_of_business"] == "CDNR-REG":
        for item in report_data[:-1]:
            res.setdefault(item["billing_address_gstin"], {}).setdefault(
                item["invoice_number"], []
            ).append(item)

        out = get_cdnr_reg_json(res, gstin)
        gst_json["cdnr"] = out
    elif filters["type_of_business"] == "CDNR-UNREG":
        for item in report_data[:-1]:
            res.setdefault(item["invoice_number"], []).append(item)

        out = get_cdnr_unreg_json(res, gstin)
        gst_json["cdnur"] = out

    elif filters["type_of_business"] in ("Advances", "Adjustment"):
        business_type_key = {
            "Advances": "at",
            "Adjustment": "txpd",
        }

        for item in report_data[:-1]:
            if not item.get("place_of_supply"):
                frappe.throw(
                    _(
                        """{0} not entered in some entries.
                        Please update and try again"""
                    ).format(frappe.bold("Place Of Supply"))
                )

            res.setdefault(item["place_of_supply"], []).append(item)

        out = get_advances_json(res, gstin)
        gst_json[business_type_key[filters.get("type_of_business")]] = out

    elif filters["type_of_business"] == "NIL Rated":
        res = report_data[:-1]
        out = get_exempted_json(res)
        gst_json["nil"] = out

    return {
        "report_name": report_name,
        "report_type": filters["type_of_business"],
        "data": gst_json,
    }


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
            out["inv"][i]["nil_amt"] = data[i]["nil_rated"]

        if data[i].get("exempted"):
            out["inv"][i]["expt_amt"] = data[i]["exempted"]

        if data[i].get("non_gst"):
            out["inv"][i]["ngsup_amt"] = data[i]["non_gst"]

    return out


def get_invoice_type(row):
    gst_category = row.get("gst_category")

    if gst_category == "SEZ":
        return "SEWP" if row.get("export_type") == "WPAY" else "SEWOP"

    if gst_category == "Overseas":
        return "EXPWP" if row.get("export_type") == "WPAY" else "EXPWOP"

    return (
        {
            "Deemed Export": "DE",
            "Registered Regular": "R",
            "Registered Composition": "R",
            "Tax Deductor": "R",
            "UIN Holders": "R",
            "Unregistered": "B2CL",
        }
    ).get(gst_category)


def get_basic_invoice_detail(row):
    return {
        "inum": row["invoice_number"],
        "idt": getdate(row["posting_date"]).strftime("%d-%m-%Y"),
        "val": flt(row["invoice_value"], 2),
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
        filters = [
            ["is_your_company_address", "=", 1],
            ["Dynamic Link", "link_doctype", "=", "Company"],
            ["Dynamic Link", "link_name", "=", company],
            ["Dynamic Link", "parenttype", "=", "Address"],
            ["gstin", "!=", ""],
        ]
        gstin = frappe.get_all(
            "Address",
            filters=filters,
            pluck="gstin",
            order_by="is_primary_address desc",
        )
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
    frappe.response["filename"] = (
        frappe.scrub("{0} {1}".format(data["report_name"], data["report_type"]))
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
