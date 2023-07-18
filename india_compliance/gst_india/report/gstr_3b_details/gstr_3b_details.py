# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.query_builder import Case
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import LiteralValue, Sum
from frappe.utils import cint, get_first_day, get_last_day

from india_compliance.gst_india.utils import get_gst_accounts_by_type


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
                "label": "Voucher Type",
                "fieldtype": "Data",
                "width": 100,
            },
            {
                "fieldname": "voucher_no",
                "label": "Voucher No",
                "fieldtype": "Link",
                "options": "Purchase Invoice",
            },
            {
                "fieldname": "posting_date",
                "label": "Posting Date",
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
                    "fieldname": "integrated_tax",
                    "label": "Integrated Tax",
                    "fieldtype": "Currency",
                    "width": 100,
                },
                {
                    "fieldname": "central_tax",
                    "label": "Central Tax",
                    "fieldtype": "Currency",
                    "width": 100,
                },
                {
                    "fieldname": "state_tax",
                    "label": "State/UT Tax",
                    "fieldtype": "Currency",
                    "width": 100,
                },
                {
                    "fieldname": "cess_amount",
                    "label": "Cess Tax",
                    "fieldtype": "Currency",
                    "width": 100,
                },
                {
                    "fieldname": "eligibility_for_itc",
                    "label": "Eligibility for ITC",
                    "fieldtype": "Data",
                    "width": 100,
                },
            ]
        )

    def get_data(self):
        purchase_data = self.get_itc_from_purchase()
        boe_data = self.get_itc_from_boe()
        journal_entry_data = self.get_itc_from_journal_entry()

        data = purchase_data + boe_data + journal_entry_data

        self.data = sorted(
            data,
            key=lambda k: (k["eligibility_for_itc"], k["posting_date"]),
        )

    def get_itc_from_purchase(self):
        purchase_invoice = frappe.qb.DocType("Purchase Invoice")

        query = (
            frappe.qb.from_(purchase_invoice)
            .select(
                ConstantColumn("Purchase Invoice").as_("voucher_type"),
                purchase_invoice.name.as_("voucher_no"),
                purchase_invoice.posting_date,
                purchase_invoice.eligibility_for_itc,
                Sum(purchase_invoice.itc_integrated_tax).as_("integrated_tax"),
                Sum(purchase_invoice.itc_central_tax).as_("central_tax"),
                Sum(purchase_invoice.itc_state_tax).as_("state_tax"),
                Sum(purchase_invoice.itc_cess_amount).as_("cess_amount"),
            )
            .where(
                (purchase_invoice.docstatus == 1)
                & (purchase_invoice.posting_date[self.from_date : self.to_date])
                & (purchase_invoice.company == self.company)
                & (purchase_invoice.company_gstin == self.company_gstin)
            )
            .groupby(purchase_invoice.name)
        )

        return query.run(as_dict=True)

    def get_itc_from_boe(self):
        boe = frappe.qb.DocType("Bill of Entry")
        boe_taxes = frappe.qb.DocType("Bill of Entry Taxes")
        self.gst_accounts = get_gst_accounts_by_type(self.company, "Input")

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
                ).as_("integrated_tax"),
                Sum(
                    Case()
                    .when(
                        boe_taxes.account_head == self.gst_accounts.cess_account,
                        boe_taxes.tax_amount,
                    )
                    .else_(0)
                ).as_("cess_amount"),
                LiteralValue(0).as_("central_tax"),
                LiteralValue(0).as_("state_tax"),
                ConstantColumn("Import of Goods").as_("eligibility_for_itc"),
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
                ).as_("integrated_tax"),
                Sum(
                    Case()
                    .when(
                        journal_entry_account.account == self.gst_accounts.cgst_account,
                        (-1 * journal_entry_account.credit_in_account_currency),
                    )
                    .else_(0)
                ).as_("central_tax"),
                Sum(
                    Case()
                    .when(
                        journal_entry_account.account == self.gst_accounts.sgst_account,
                        (-1 * journal_entry_account.credit_in_account_currency),
                    )
                    .else_(0)
                ).as_("state_tax"),
                Sum(
                    Case()
                    .when(
                        journal_entry_account.account == self.gst_accounts.cess_account,
                        (-1 * journal_entry_account.credit_in_account_currency),
                    )
                    .else_(0)
                ).as_("cess_amount"),
                journal_entry.reversal_type.as_("eligibility_for_itc"),
            )
            .where(
                (journal_entry.docstatus == 1)
                & (journal_entry.posting_date[self.from_date : self.to_date])
                & (journal_entry.company == self.company)
                & (journal_entry.company_gstin == self.company_gstin)
                & (journal_entry.voucher_type == "Reversal of ITC")
            )
            .groupby(journal_entry.name)
        )
        return query.run(as_dict=True)


class GSTR3B_Inward_Nil_Exempt(BaseGSTR3BDetails):
    def extend_columns(self):
        self.columns.extend(
            [
                {
                    "fieldname": "intra",
                    "label": "Intra State",
                    "fieldtype": "Currency",
                    "width": 100,
                },
                {
                    "fieldname": "inter",
                    "label": "Inter State",
                    "fieldtype": "Currency",
                    "width": 100,
                },
                {
                    "fieldname": "nature_of_supply",
                    "label": "Nature of Supply",
                    "fieldtype": "Data",
                    "width": 100,
                },
            ]
        )

    def get_data(self):
        formatted_data = []

        invoices = self.get_inward_nil_exempt()

        address_state_map = self.get_address_state_map()

        state = self.company_gstin[0:2]

        for invoice in invoices:
            place_of_supply = cint(invoice.place_of_supply.split("-")[0] or state)

            supplier_state = cint(
                address_state_map.get(invoice.supplier_address) or state
            )
            intra, inter = 0, 0
            base_amount = invoice.base_amount

            if (
                invoice.is_nil_exempt == 1
                or invoice.get("gst_category") == "Registered Composition"
            ):
                if supplier_state == place_of_supply:
                    intra = base_amount
                else:
                    inter = base_amount

                nature_of_supply = "Composition Scheme, Exempted, Nil Rated"

            elif invoice.is_non_gst == 1:
                if supplier_state == place_of_supply:
                    intra = base_amount
                else:
                    inter = base_amount

                nature_of_supply = "Non GST Supply"

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
                Sum(purchase_invoice_item.base_amount).as_("base_amount"),
                purchase_invoice_item.is_nil_exempt,
                purchase_invoice_item.is_non_gst,
                purchase_invoice.supplier_gstin,
                purchase_invoice.supplier_address,
            )
            .where(
                (purchase_invoice.docstatus == 1)
                & (purchase_invoice.is_opening == "No")
                & (purchase_invoice.name == purchase_invoice_item.parent)
                & (
                    (purchase_invoice_item.is_nil_exempt == 1)
                    | (purchase_invoice_item.is_non_gst == 1)
                    | (purchase_invoice.gst_category == "Registered Composition")
                )
                & (purchase_invoice.posting_date[self.from_date : self.to_date])
                & (purchase_invoice.company == self.company)
                & (purchase_invoice.company_gstin == self.company_gstin)
            )
            .groupby(purchase_invoice.name)
        )

        return query.run(as_dict=True)
