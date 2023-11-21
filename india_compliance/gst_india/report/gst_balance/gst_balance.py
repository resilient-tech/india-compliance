# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import cstr

from india_compliance.gst_india.utils import get_all_gst_accounts, get_gstin_list
from india_compliance.patches.post_install.update_company_gstin import (
    execute as _update_company_gstin,
)
from india_compliance.patches.post_install.update_company_gstin import (
    verify_gstin_update,
)


def execute(filters=None):
    if get_pending_voucher_types(filters.get("company"))[0]:
        frappe.msgprint(
            _("Update Company GSTIN before generating GST Balance Report"),
            alert=True,
            indicator="red",
        )

        return [], []

    report = GSTBalanceReport(filters)
    columns = report.get_columns()

    if not filters.show_summary:
        data = report.get_trial_balance_data()

    else:
        data = report.get_summary_data()

    return columns, data


@frappe.whitelist()
def get_pending_voucher_types(company=None):
    frappe.has_permission("GST Settings", "write", throw=True)

    company_accounts = ""
    if company:
        company_accounts = get_all_gst_accounts(company)

    return verify_gstin_update(company_accounts), company_accounts


@frappe.whitelist()
def update_company_gstin():
    frappe.has_permission("GST Settings", "write", throw=True)
    return _update_company_gstin()


class GSTBalanceReport:
    def __init__(self, filters=None):
        self.filters = frappe._dict(filters or {})
        self.validate_filters()
        self.gst_accounts = get_all_gst_accounts(filters.company)
        self.gl_entry = frappe.qb.DocType("GL Entry")
        self.default_finance_book = frappe.get_cached_value(
            "Company", self.filters.company, "default_finance_book"
        )

    def validate_filters(self):
        if not self.filters.company:
            frappe.throw(_("Please select a Company"))

        if not self.filters.from_date and not self.filters.show_summary:
            frappe.throw(_("Please select a From Date"))

        if not self.filters.to_date:
            frappe.throw(_("Please select a To Date"))

        if self.filters.from_date and self.filters.from_date > self.filters.to_date:
            frappe.throw(_("From Date cannot be greater than To Date"))

    def get_columns(self):
        if not self.filters.show_summary:
            return [
                {
                    "fieldname": "account",
                    "label": _("Account"),
                    "fieldtype": "Link",
                    "options": "Account",
                    "width": 250,
                },
                {
                    "fieldname": "opening_debit",
                    "label": _("Opening (Dr)"),
                    "fieldtype": "Currency",
                    "options": "Company:company:default_currency",
                    "width": 150,
                },
                {
                    "fieldname": "opening_credit",
                    "label": _("Opening (Cr)"),
                    "fieldtype": "Currency",
                    "options": "Company:company:default_currency",
                    "width": 150,
                },
                {
                    "fieldname": "debit",
                    "label": _("Debit"),
                    "fieldtype": "Currency",
                    "options": "Company:company:default_currency",
                    "width": 150,
                },
                {
                    "fieldname": "credit",
                    "label": _("Credit"),
                    "fieldtype": "Currency",
                    "options": "Company:company:default_currency",
                    "width": 150,
                },
                {
                    "fieldname": "closing_debit",
                    "label": _("Closing (Dr)"),
                    "fieldtype": "Currency",
                    "options": "Company:company:default_currency",
                    "width": 150,
                },
                {
                    "fieldname": "closing_credit",
                    "label": _("Closing (Cr)"),
                    "fieldtype": "Currency",
                    "options": "Company:company:default_currency",
                    "width": 150,
                },
            ]

        else:
            columns = [
                {
                    "fieldname": "account",
                    "label": _("Account"),
                    "fieldtype": "Link",
                    "options": "Account",
                    "width": 250,
                }
            ]

            self.company_gstins = get_gstin_list(self.filters.company)
            for gstin in self.company_gstins:
                columns.append(
                    {
                        "fieldname": f"gstin_{gstin}",
                        "label": gstin,
                        "fieldtype": "Currency",
                        "options": "Company:company:default_currency",
                        "width": 150,
                    }
                )

            return columns

    def get_trial_balance_data(self):
        opening_balance = self.get_opening_balance()
        transactions = self.get_transactions()

        def _process_opening_balance(account, is_debit=True):
            row = opening_balance.get(account, {})
            balance = row.get("debit", 0) - row.get("credit", 0)

            if is_debit:
                return max(balance, 0)
            else:
                return max(-balance, 0)

        data = frappe._dict()
        for account in self.gst_accounts:
            transaction = transactions.get(account, {})
            data[account] = frappe._dict(
                {
                    "account": account,
                    "opening_debit": _process_opening_balance(account, is_debit=True),
                    "opening_credit": _process_opening_balance(account, is_debit=False),
                    "debit": transaction.get("debit", 0),
                    "credit": transaction.get("credit", 0),
                    "closing_debit": 0,
                    "closing_credit": 0,
                }
            )

            closing_balance = (
                data[account]["opening_debit"] + data[account]["debit"]
            ) - (data[account]["opening_credit"] + data[account]["credit"])

            if closing_balance > 0:
                data[account]["closing_debit"] = closing_balance
            else:
                data[account]["closing_credit"] = abs(closing_balance)

        return list(data.values())

    def get_summary_data(self):
        data = frappe._dict()
        for company_gstin in self.company_gstins:
            self.filters.company_gstin = company_gstin
            balance = self.get_closing_balance()

            for account in self.gst_accounts:
                data.setdefault(account, frappe._dict(account=account))
                row = balance.get(account, {})

                data[account][f"gstin_{company_gstin}"] = row.get("debit", 0) - row.get(
                    "credit", 0
                )

        return list(data.values())

    def get_transactions(self):
        return self.get_account_wise_dict(
            self.get_gl_query()
            .where(
                (self.gl_entry.posting_date >= self.filters.from_date)
                & (self.gl_entry.posting_date <= self.filters.to_date)
                & (self.gl_entry.is_opening == "No")
            )
            .run(as_dict=True)
        )

    def get_opening_balance(self):
        return self.get_account_wise_dict(
            self.get_gl_query()
            .where(
                (self.gl_entry.posting_date < self.filters.from_date)
                | (
                    (self.gl_entry.posting_date >= self.filters.from_date)
                    & (self.gl_entry.posting_date <= self.filters.to_date)
                    & (self.gl_entry.is_opening == "Yes")
                )
            )
            .run(as_dict=True)
        )

    def get_closing_balance(self):
        return self.get_account_wise_dict(
            self.get_gl_query()
            .where((self.gl_entry.posting_date <= self.filters.to_date))
            .run(as_dict=True)
        )

    def get_gl_query(self):
        query = (
            frappe.qb.from_(self.gl_entry)
            .select(
                self.gl_entry.account,
                Sum(self.gl_entry.debit).as_("debit"),
                Sum(self.gl_entry.credit).as_("credit"),
            )
            .where(self.gl_entry.is_cancelled == 0)
            .where(self.gl_entry.company == self.filters.company)
            .where(self.gl_entry.account.isin(self.gst_accounts))
            .where(
                (self.gl_entry.finance_book.isin(["", cstr(self.default_finance_book)]))
                | (self.gl_entry.finance_book.isnull())
            )
            .groupby(self.gl_entry.account)
        )

        if self.filters.company_gstin:
            query = query.where(
                self.gl_entry.company_gstin == self.filters.company_gstin
            )

        return query

    def get_account_wise_dict(self, data):
        return {d.account: d for d in data}
