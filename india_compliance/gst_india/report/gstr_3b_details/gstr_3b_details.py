# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import Case, DatePart
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import Extract, Ifnull, IfNull, LiteralValue, Sum
from frappe.utils import cint, get_first_day, get_last_day


def execute(filters=None):
    if not filters.get("section"):
        return

    report_type = filters.get("section")

    if report_type == "4":
        report = GSTR3B_ITC_Details(filters)

    elif report_type == "5":
        report = GSTR3B_Inward_Nil_Exempt(filters)

    return report.run()


class BaseGSTR3BDetails:
    def __init__(self, filters=None):
        self.filters = frappe._dict(filters or {})
        self.company_currency = frappe.get_cached_value(
            "Company", filters.get("company"), "default_currency"
        )

        self.columns = [
            {
                "fieldname": "voucher_type",
                "label": _("Voucher Type"),
                "fieldtype": "Data",
                "width": 100,
            },
            {
                "fieldname": "voucher_no",
                "label": _("Voucher No"),
                "fieldtype": "Dynamic Link",
                "options": "voucher_type",
            },
            {
                "fieldname": "posting_date",
                "label": _("Posting Date"),
                "fieldtype": "Date",
                "width": 100,
            },
        ]
        self.data = []
        self.from_date = get_first_day(
            f"{cint(self.filters.year)}-{cint(self.filters.month)}-01"
        )
        self.to_date = get_last_day(
            f"{cint(self.filters.year)}-{cint(self.filters.month)}-01"
        )
        self.company = self.filters.company
        self.company_gstin = self.filters.company_gstin

    def run(self):
        self.extend_columns()
        self.get_data()

        return self.columns, self.data

    def extend_columns(self):
        raise NotImplementedError("Report Not Available")

    def get_data(self):
        raise NotImplementedError("Report Not Available")


class GSTR3B_ITC_Details(BaseGSTR3BDetails):
    def extend_columns(self):
        self.columns.extend(
            [
                {
                    "fieldname": "iamt",
                    "label": _("Integrated Tax"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 100,
                },
                {
                    "fieldname": "camt",
                    "label": _("Central Tax"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 100,
                },
                {
                    "fieldname": "samt",
                    "label": _("State/UT Tax"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 100,
                },
                {
                    "fieldname": "csamt",
                    "label": _("Cess Tax"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 100,
                },
                {
                    "fieldname": "itc_classification",
                    "label": _("Eligibility for ITC"),
                    "fieldtype": "Data",
                    "width": 100,
                },
            ]
        )

    def get_data(self):
        purchase_data = self.get_itc_from_purchase()
        boe_data = self.get_itc_from_boe()
        journal_entry_data = self.get_itc_from_journal_entry()
        pi_ineligible_itc = self.get_ineligible_itc_from_purchase()
        boe_ineligible_itc = self.get_ineligible_itc_from_boe()

        data = (
            purchase_data
            + boe_data
            + journal_entry_data
            + pi_ineligible_itc
            + boe_ineligible_itc
        )

        self.data = sorted(
            data,
            key=lambda k: (k["itc_classification"], k["posting_date"]),
        )

    def get_itc_from_purchase(self):
        purchase_invoice = frappe.qb.DocType("Purchase Invoice")

        query = (
            frappe.qb.from_(purchase_invoice)
            .select(
                ConstantColumn("Purchase Invoice").as_("voucher_type"),
                purchase_invoice.name.as_("voucher_no"),
                purchase_invoice.posting_date,
                purchase_invoice.itc_classification,
                Sum(purchase_invoice.itc_integrated_tax).as_("iamt"),
                Sum(purchase_invoice.itc_central_tax).as_("camt"),
                Sum(purchase_invoice.itc_state_tax).as_("samt"),
                Sum(purchase_invoice.itc_cess_amount).as_("csamt"),
            )
            .where(
                (purchase_invoice.docstatus == 1)
                & (purchase_invoice.is_opening == "No")
                & (purchase_invoice.posting_date[self.from_date : self.to_date])
                & (purchase_invoice.company == self.company)
                & (purchase_invoice.company_gstin == self.company_gstin)
                & (
                    purchase_invoice.company_gstin
                    != IfNull(purchase_invoice.supplier_gstin, "")
                )
                & (Ifnull(purchase_invoice.itc_classification, "") != "")
            )
            .groupby(purchase_invoice.name)
        )

        return query.run(as_dict=True)

    def get_itc_from_boe(self):
        boe = frappe.qb.DocType("Bill of Entry")
        boe_taxes = frappe.qb.DocType("Bill of Entry Taxes")

        query = (
            frappe.qb.from_(boe)
            .join(boe_taxes)
            .on(boe_taxes.parent == boe.name)
            .select(
                ConstantColumn("Bill of Entry").as_("voucher_type"),
                boe.name.as_("voucher_no"),
                boe.posting_date,
                Sum(
                    Case()
                    .when(
                        boe_taxes.gst_tax_type == "igst",
                        boe_taxes.tax_amount,
                    )
                    .else_(0)
                ).as_("iamt"),
                Sum(
                    Case()
                    .when(
                        boe_taxes.gst_tax_type.isin(["cess", "cess_non_advol"]),
                        boe_taxes.tax_amount,
                    )
                    .else_(0)
                ).as_("csamt"),
                LiteralValue(0).as_("camt"),
                LiteralValue(0).as_("samt"),
                ConstantColumn("Import Of Goods").as_("itc_classification"),
            )
            .where(
                (boe.docstatus == 1)
                & (boe.posting_date[self.from_date : self.to_date])
                & (boe.company == self.company)
                & (boe.company_gstin == self.company_gstin)
            )
            .groupby(boe.name)
        )

        return query.run(as_dict=True)

    def get_itc_from_journal_entry(self):
        journal_entry = frappe.qb.DocType("Journal Entry")
        journal_entry_account = frappe.qb.DocType("Journal Entry Account")

        query = (
            frappe.qb.from_(journal_entry)
            .join(journal_entry_account)
            .on(journal_entry_account.parent == journal_entry.name)
            .select(
                ConstantColumn("Journal Entry").as_("voucher_type"),
                journal_entry.name.as_("voucher_no"),
                journal_entry.posting_date,
                Sum(
                    Case()
                    .when(
                        journal_entry_account.gst_tax_type == "igst",
                        (-1 * journal_entry_account.credit_in_account_currency),
                    )
                    .else_(0)
                ).as_("iamt"),
                Sum(
                    Case()
                    .when(
                        journal_entry_account.gst_tax_type == "cgst",
                        (-1 * journal_entry_account.credit_in_account_currency),
                    )
                    .else_(0)
                ).as_("camt"),
                Sum(
                    Case()
                    .when(
                        journal_entry_account.gst_tax_type == "sgst",
                        (-1 * journal_entry_account.credit_in_account_currency),
                    )
                    .else_(0)
                ).as_("samt"),
                Sum(
                    Case()
                    .when(
                        journal_entry_account.gst_tax_type.isin(
                            ["cess", "cess_non_advol"]
                        ),
                        (-1 * journal_entry_account.credit_in_account_currency),
                    )
                    .else_(0)
                ).as_("csamt"),
                journal_entry.ineligibility_reason.as_("itc_classification"),
            )
            .where(
                (journal_entry.docstatus == 1)
                & (journal_entry.is_opening == "No")
                & (journal_entry.posting_date[self.from_date : self.to_date])
                & (journal_entry.company == self.company)
                & (journal_entry.company_gstin == self.company_gstin)
                & (journal_entry.voucher_type == "Reversal of ITC")
            )
            .groupby(journal_entry.name)
        )
        return query.run(as_dict=True)

    def get_ineligible_itc_from_purchase(self):
        ineligible_itc = IneligibleITC(
            self.company, self.company_gstin, self.filters.month, self.filters.year
        ).get_for_purchase("Ineligible As Per Section 17(5)")

        return self.process_ineligible_itc(ineligible_itc)

    def get_ineligible_itc_from_boe(self):
        ineligible_itc = IneligibleITC(
            self.company, self.company_gstin, self.filters.month, self.filters.year
        ).get_for_bill_of_entry()

        return self.process_ineligible_itc(ineligible_itc)

    def process_ineligible_itc(self, ineligible_itc):
        if not ineligible_itc:
            return []

        for row in ineligible_itc.copy():
            for key in ["iamt", "camt", "samt", "csamt"]:
                row[key] = row[key] * -1

        return ineligible_itc


class GSTR3B_Inward_Nil_Exempt(BaseGSTR3BDetails):
    def extend_columns(self):
        self.columns.extend(
            [
                {
                    "fieldname": "intra",
                    "label": _("Intra State"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 100,
                },
                {
                    "fieldname": "inter",
                    "label": _("Inter State"),
                    "fieldtype": "Currency",
                    "options": self.company_currency,
                    "width": 100,
                },
                {
                    "fieldname": "nature_of_supply",
                    "label": _("Nature of Supply"),
                    "fieldtype": "Data",
                    "width": 100,
                },
            ]
        )

    def get_data(self):
        formatted_data = []

        invoices = self.get_inward_nil_exempt()

        address_state_map = self.get_address_state_map()

        state = cint(self.company_gstin[0:2])

        for invoice in invoices:
            place_of_supply = cint(invoice.place_of_supply[0:2]) or state

            nature_of_supply = ""

            if invoice.gst_category == "Registered Composition":
                supplier_state = cint(invoice.supplier_gstin[0:2])
            else:
                supplier_state = (
                    cint(address_state_map.get(invoice.supplier_address)) or state
                )

            intra, inter = 0, 0
            taxable_value = invoice.taxable_value

            if (
                invoice.gst_treatment in ["Nil-Rated", "Exempted"]
                or invoice.get("gst_category") == "Registered Composition"
            ):
                nature_of_supply = "Composition Scheme, Exempted, Nil Rated"

            elif invoice.gst_treatment == "Non-GST":
                nature_of_supply = "Non GST Supply"

            if supplier_state == place_of_supply:
                intra = taxable_value
            else:
                inter = taxable_value

            formatted_data.append(
                {
                    **invoice,
                    "intra": intra,
                    "inter": inter,
                    "nature_of_supply": nature_of_supply,
                }
            )

        self.data = sorted(
            formatted_data, key=lambda k: (k["nature_of_supply"], k["posting_date"])
        )

    def get_address_state_map(self):
        return frappe._dict(
            frappe.get_all("Address", fields=["name", "gst_state_number"], as_list=1)
        )

    def get_inward_nil_exempt(self):
        purchase_invoice = frappe.qb.DocType("Purchase Invoice")
        purchase_invoice_item = frappe.qb.DocType("Purchase Invoice Item")

        query = (
            frappe.qb.from_(purchase_invoice)
            .join(purchase_invoice_item)
            .on(purchase_invoice_item.parent == purchase_invoice.name)
            .select(
                ConstantColumn("Purchase Invoice").as_("voucher_type"),
                purchase_invoice.name.as_("voucher_no"),
                purchase_invoice.posting_date,
                purchase_invoice.place_of_supply,
                purchase_invoice.supplier_address,
                Sum(purchase_invoice_item.taxable_value).as_("taxable_value"),
                purchase_invoice_item.gst_treatment,
                purchase_invoice.supplier_gstin,
                purchase_invoice.supplier_address,
            )
            .where(
                (purchase_invoice.docstatus == 1)
                & (purchase_invoice.is_opening == "No")
                & (purchase_invoice.name == purchase_invoice_item.parent)
                & (
                    (purchase_invoice_item.gst_treatment != "Taxable")
                    | (purchase_invoice.gst_category == "Registered Composition")
                )
                & (purchase_invoice.posting_date[self.from_date : self.to_date])
                & (purchase_invoice.company == self.company)
                & (purchase_invoice.company_gstin == self.company_gstin)
                & (
                    purchase_invoice.company_gstin
                    != IfNull(purchase_invoice.supplier_gstin, "")
                )
            )
            .groupby(purchase_invoice.name)
        )

        return query.run(as_dict=True)


class IneligibleITC:
    def __init__(self, company, gstin, month, year) -> None:
        self.company = company
        self.gstin = gstin
        self.month = month
        self.year = year

    def get_for_purchase(self, ineligibility_reason, group_by="name"):
        doctype = "Purchase Invoice"
        dt = frappe.qb.DocType(doctype)
        dt_item = frappe.qb.DocType(f"{doctype} Item")

        query = (
            self.get_common_query(doctype, dt, dt_item)
            .select((dt.ineligibility_reason).as_("itc_classification"))
            .where((dt.is_opening == "No"))
            .where(IfNull(dt.ineligibility_reason, "") == ineligibility_reason)
        )

        if ineligibility_reason == "Ineligible As Per Section 17(5)":
            query = query.where(dt_item.is_ineligible_for_itc == 1)

        return query.groupby(dt[group_by]).run(as_dict=True)

    def get_for_bill_of_entry(self, group_by="name"):
        doctype = "Bill of Entry"
        dt = frappe.qb.DocType(doctype)
        dt_item = frappe.qb.DocType(f"{doctype} Item")
        query = (
            self.get_common_query(doctype, dt, dt_item)
            .select(
                ConstantColumn("Ineligible As Per Section 17(5)").as_(
                    "itc_classification"
                )
            )
            .where(dt_item.is_ineligible_for_itc == 1)
        )

        return query.groupby(dt[group_by]).run(as_dict=True)

    def get_common_query(self, doctype, dt, dt_item):
        return (
            frappe.qb.from_(dt)
            .join(dt_item)
            .on(dt.name == dt_item.parent)
            .select(
                ConstantColumn(doctype).as_("voucher_type"),
                dt.name.as_("voucher_no"),
                dt.posting_date,
                Sum(dt_item.igst_amount).as_("iamt"),
                Sum(dt_item.cgst_amount).as_("camt"),
                Sum(dt_item.sgst_amount).as_("samt"),
                Sum(dt_item.cess_amount + dt_item.cess_non_advol_amount).as_("csamt"),
            )
            .where(dt.docstatus == 1)
            .where(dt.company_gstin == self.gstin)
            .where(dt.company == self.company)
            .where(Extract(DatePart.month, dt.posting_date).eq(self.month))
            .where(Extract(DatePart.year, dt.posting_date).eq(self.year))
        )
