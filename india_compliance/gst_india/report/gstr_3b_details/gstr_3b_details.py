# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import Case, DatePart
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import Extract, Ifnull, IfNull, LiteralValue, Sum
from frappe.utils import cint, flt, get_first_day, get_last_day

from india_compliance.gst_india.utils import get_escaped_gst_accounts


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
                    "options": "Company:company:default_currency",
                    "width": 100,
                },
                {
                    "fieldname": "camt",
                    "label": _("Central Tax"),
                    "fieldtype": "Currency",
                    "options": "Company:company:default_currency",
                    "width": 100,
                },
                {
                    "fieldname": "samt",
                    "label": _("State/UT Tax"),
                    "fieldtype": "Currency",
                    "options": "Company:company:default_currency",
                    "width": 100,
                },
                {
                    "fieldname": "csamt",
                    "label": _("Cess Tax"),
                    "fieldtype": "Currency",
                    "options": "Company:company:default_currency",
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
        self.gst_accounts = get_escaped_gst_accounts(self.company, "Input")
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
                        boe_taxes.account_head == self.gst_accounts.igst_account,
                        boe_taxes.tax_amount,
                    )
                    .else_(0)
                ).as_("iamt"),
                Sum(
                    Case()
                    .when(
                        boe_taxes.account_head == self.gst_accounts.cess_account,
                        boe_taxes.tax_amount,
                    )
                    .else_(0)
                ).as_("csamt"),
                LiteralValue(0).as_("camt"),
                LiteralValue(0).as_("samt"),
                ConstantColumn("Import of Goods").as_("itc_classification"),
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
                        journal_entry_account.account == self.gst_accounts.igst_account,
                        (-1 * journal_entry_account.credit_in_account_currency),
                    )
                    .else_(0)
                ).as_("iamt"),
                Sum(
                    Case()
                    .when(
                        journal_entry_account.account == self.gst_accounts.cgst_account,
                        (-1 * journal_entry_account.credit_in_account_currency),
                    )
                    .else_(0)
                ).as_("camt"),
                Sum(
                    Case()
                    .when(
                        journal_entry_account.account == self.gst_accounts.sgst_account,
                        (-1 * journal_entry_account.credit_in_account_currency),
                    )
                    .else_(0)
                ).as_("samt"),
                Sum(
                    Case()
                    .when(
                        journal_entry_account.account == self.gst_accounts.cess_account,
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
        ).get_for_purchase_invoice()

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
            if row.itc_classification == "ITC restricted due to PoS rules":
                ineligible_itc.remove(row)
                continue

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
                    "options": "Company:company:default_currency",
                    "width": 100,
                },
                {
                    "fieldname": "inter",
                    "label": _("Inter State"),
                    "fieldtype": "Currency",
                    "options": "Company:company:default_currency",
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
            )
            .groupby(purchase_invoice.name)
        )

        return query.run(as_dict=True)


class IneligibleITC:
    def __init__(self, company, gstin, month, year) -> None:
        self.gl_entry = frappe.qb.DocType("GL Entry")
        self.company = company
        self.gstin = gstin
        self.month = month
        self.year = year
        self.gst_accounts = get_escaped_gst_accounts(company, "Input")

    def get_for_purchase_invoice(self, group_by="name"):
        ineligible_transactions = self.get_vouchers_with_gst_expense("Purchase Invoice")

        if not ineligible_transactions:
            return

        pi = frappe.qb.DocType("Purchase Invoice")

        credit_availed = (
            self.get_gl_entry_query("Purchase Invoice")
            .inner_join(pi)
            .on(pi.name == self.gl_entry.voucher_no)
            .select(*self.select_net_gst_amount_from_gl_entry())
            .select(
                pi.name.as_("voucher_no"),
                pi.ineligibility_reason.as_("itc_classification"),
            )
            .where(IfNull(pi.ineligibility_reason, "") != "")
            .where(pi.name.isin(ineligible_transactions))
            .groupby(pi[group_by])
            .run(as_dict=1)
        )

        credit_available = (
            frappe.qb.from_(pi)
            .select(
                ConstantColumn("Purchase Invoice").as_("voucher_type"),
                pi.name.as_("voucher_no"),
                pi.posting_date,
                pi.ineligibility_reason.as_("itc_classification"),
                Sum(pi.itc_integrated_tax).as_("iamt"),
                Sum(pi.itc_central_tax).as_("camt"),
                Sum(pi.itc_state_tax).as_("samt"),
                Sum(pi.itc_cess_amount).as_("csamt"),
            )
            .where(IfNull(pi.ineligibility_reason, "") != "")
            .where(pi.name.isin(ineligible_transactions))
            .groupby(pi[group_by])
            .run(as_dict=1)
        )

        return self.get_ineligible_credit(credit_availed, credit_available, group_by)

    def get_for_bill_of_entry(self, group_by="name"):
        ineligible_transactions = self.get_vouchers_with_gst_expense("Bill of Entry")

        if not ineligible_transactions:
            return

        boe = frappe.qb.DocType("Bill of Entry")
        boe_taxes = frappe.qb.DocType("Bill of Entry Taxes")

        credit_availed = (
            self.get_gl_entry_query("Bill of Entry")
            .inner_join(boe)
            .on(boe.name == self.gl_entry.voucher_no)
            .select(*self.select_net_gst_amount_from_gl_entry())
            .select(
                boe.name.as_("voucher_no"),
                ConstantColumn("Ineligible As Per Section 17(5)").as_(
                    "itc_classification"
                ),
            )
            .where(boe.name.isin(ineligible_transactions))
            .groupby(boe[group_by])
            .run(as_dict=1)
        )

        credit_available = (
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
                        boe_taxes.account_head == self.gst_accounts.igst_account,
                        boe_taxes.tax_amount,
                    )
                    .else_(0)
                ).as_("iamt"),
                Sum(
                    Case()
                    .when(
                        boe_taxes.account_head == self.gst_accounts.cess_account,
                        boe_taxes.tax_amount,
                    )
                    .else_(0)
                ).as_("csamt"),
                LiteralValue(0).as_("camt"),
                LiteralValue(0).as_("samt"),
                ConstantColumn("Ineligible As Per Section 17(5)").as_(
                    "itc_classification"
                ),
            )
            .where(boe.name.isin(ineligible_transactions))
            .groupby(boe[group_by])
            .run(as_dict=1)
        )

        return self.get_ineligible_credit(credit_availed, credit_available, group_by)

    def get_ineligible_credit(self, credit_availed, credit_available, group_by):
        if group_by == "name":
            group_by_field = "voucher_no"
        elif group_by == "ineligibility_reason":
            group_by_field = "itc_classification"
        else:
            group_by_field = group_by

        credit_availed_dict = frappe._dict(
            {d[group_by_field]: d for d in credit_availed}
        )
        ineligible_credit = []
        tax_amounts = ["camt", "samt", "iamt", "csamt"]

        for row in credit_available:
            credit_availed = credit_availed_dict.get(row[group_by_field])
            if not credit_availed:
                ineligible_credit.append(row)
                continue

            for key in tax_amounts:
                if key not in row:
                    continue

                row[key] -= flt(credit_availed.get(key, 0))

            ineligible_credit.append(row)

        return ineligible_credit

    def get_vouchers_with_gst_expense(self, voucher_type):
        gst_expense_account = frappe.get_cached_value(
            "Company", self.company, "default_gst_expense_account"
        )

        data = (
            self.get_gl_entry_query(voucher_type)
            .select(self.gl_entry.voucher_no)
            .where(self.gl_entry.account == gst_expense_account)
            .run(as_dict=1)
        )

        return set([d.voucher_no for d in data])

    def select_net_gst_amount_from_gl_entry(self):
        account_field_map = {
            "cgst_account": "camt",
            "sgst_account": "samt",
            "igst_account": "iamt",
            "cess_account": "csamt",
        }
        fields = []

        for account_field, key in account_field_map.items():
            if (
                account_field not in self.gst_accounts
                or not self.gst_accounts[account_field]
            ):
                continue

            fields.append(
                (
                    Sum(
                        Case()
                        .when(
                            self.gl_entry.account.eq(self.gst_accounts[account_field]),
                            self.gl_entry.debit_in_account_currency,
                        )
                        .else_(0)
                    )
                    - Sum(
                        Case()
                        .when(
                            self.gl_entry.account.eq(self.gst_accounts[account_field]),
                            self.gl_entry.credit_in_account_currency,
                        )
                        .else_(0)
                    )
                ).as_(key)
            )

        return fields

    def get_gl_entry_query(self, voucher_type):
        query = (
            frappe.qb.from_(self.gl_entry)
            .where(self.gl_entry.docstatus == 1)
            .where(self.gl_entry.is_opening == "No")
            .where(self.gl_entry.voucher_type == voucher_type)
            .where(self.gl_entry.is_cancelled == 0)
            .where(self.gl_entry.company_gstin == self.gstin)
            .where(Extract(DatePart.month, self.gl_entry.posting_date).eq(self.month))
            .where(Extract(DatePart.year, self.gl_entry.posting_date).eq(self.year))
        )

        return query
