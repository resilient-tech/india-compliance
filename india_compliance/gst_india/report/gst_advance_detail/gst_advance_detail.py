# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

from pypika.terms import Case

import frappe
from frappe import _
from frappe.query_builder import Criterion
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import IfNull, Sum
from frappe.utils import flt, getdate

from india_compliance.gst_india.utils import get_gst_accounts_by_type


def execute(filters=None):
    report = GSTAdvanceDetail(filters)
    return report.get_columns(), report.get_data()


class GSTAdvanceDetail:
    def __init__(self, filters):
        self.filters = filters

        self.pe = frappe.qb.DocType("Payment Entry")
        self.pe_ref = frappe.qb.DocType("Payment Entry Reference")
        self.gl_entry = frappe.qb.DocType("GL Entry")
        self.gst_accounts = get_gst_accounts(filters)

    def get_columns(self):
        columns = [
            {
                "fieldname": "posting_date",
                "label": _("Posting Date"),
                "fieldtype": "Date",
                "width": 120,
            },
            {
                "fieldname": "payment_entry",
                "label": _("Payment Entry"),
                "fieldtype": "Link",
                "options": "Payment Entry",
                "width": 180,
            },
            {
                "fieldname": "customer",
                "label": _("Customer"),
                "fieldtype": "Link",
                "options": "Customer",
                "width": 150,
            },
            {
                "fieldname": "customer_name",
                "label": _("Customer Name"),
                "fieldtype": "Data",
                "width": 150,
            },
            {
                "fieldname": "paid_amount",
                "label": _("Paid Amount"),
                "fieldtype": "Currency",
                "options": "Company:company:default_currency",
                "width": 120,
            },
            {
                "fieldname": "allocated_amount",
                "label": _("Allocated Amount"),
                "fieldtype": "Currency",
                "options": "Company:company:default_currency",
                "width": 120,
            },
            {
                "fieldname": "gst_paid",
                "label": _("GST Paid"),
                "fieldtype": "Currency",
                "options": "Company:company:default_currency",
                "width": 120,
            },
            {
                "fieldname": "gst_allocated",
                "label": _("GST Allocated"),
                "fieldtype": "Currency",
                "options": "Company:company:default_currency",
                "width": 120,
            },
            {
                "fieldname": "against_voucher_type",
                "label": _("Against Voucher Type"),
                "fieldtype": "Link",
                "options": "DocType",
                "width": 150,
                "hidden": 1,
            },
            {
                "fieldname": "against_voucher",
                "label": _("Against Voucher"),
                "fieldtype": "Dynamic Link",
                "options": "against_voucher_type",
                "width": 150,
            },
            {
                "fieldname": "place_of_supply",
                "label": _("Place of Supply"),
                "fieldtype": "Data",
                "width": 150,
            },
        ]

        if not self.filters.get("show_summary"):
            return columns

        for col in columns.copy():
            if col.get("fieldname") in ["posting_date", "against_voucher"]:
                columns.remove(col)

        return columns

    def get_data(self):
        paid_entries = self.get_paid_entries()
        allocated_entries = self.get_allocated_entries()

        data = paid_entries + allocated_entries

        # sort by payment_entry
        data = sorted(data, key=lambda k: (k["payment_entry"]), reverse=True)

        if not self.filters.get("show_summary"):
            return data

        return self.get_summary_data(data)

    def get_summary_data(self, data):
        amount_fields = {
            "paid_amount": 0,
            "gst_paid": 0,
            "allocated_amount": 0,
            "gst_allocated": 0,
        }

        summary_data = {}
        for row in data:
            new_row = summary_data.setdefault(
                row["payment_entry"], {**row, **amount_fields}
            )

            for key in amount_fields:
                new_row[key] += flt(row[key])

        return list(summary_data.values())

    def get_paid_entries(self):
        return (
            self.get_query()
            .select(
                ConstantColumn(0).as_("allocated_amount"),
                ConstantColumn("").as_("against_voucher_type"),
                ConstantColumn("").as_("against_voucher"),
            )
            .where(self.gl_entry.credit_in_account_currency > 0)
            .groupby(self.gl_entry.voucher_no)
            .run(as_dict=True)
        )

    def get_allocated_entries(self):
        query = (
            self.get_query()
            .join(self.pe_ref)
            .on(self.pe_ref.name == self.gl_entry.voucher_detail_no)
            .select(
                self.pe_ref.allocated_amount,
                self.pe_ref.reference_doctype.as_("against_voucher_type"),
                self.pe_ref.reference_name.as_("against_voucher"),
            )
            .where(self.gl_entry.debit_in_account_currency > 0)
        )

        if self.filters.get("show_summary"):
            query = query.groupby(self.gl_entry.voucher_no)

        else:
            query = query.groupby(self.gl_entry.voucher_detail_no)

        return query.run(as_dict=True)

    def get_query(self):
        return (
            frappe.qb.from_(self.gl_entry)
            .join(self.pe)
            .on(self.pe.name == self.gl_entry.voucher_no)
            .select(
                self.gl_entry.voucher_no,
                self.gl_entry.posting_date,
                self.pe.name.as_("payment_entry"),
                self.pe.party.as_("customer"),
                self.pe.party_name.as_("customer_name"),
                Case()
                .when(self.gl_entry.credit_in_account_currency > 0, self.pe.paid_amount)
                .else_(0)
                .as_("paid_amount"),
                Sum(self.gl_entry.credit_in_account_currency).as_("gst_paid"),
                Sum(self.gl_entry.debit_in_account_currency).as_("gst_allocated"),
                self.pe.place_of_supply,
            )
            .where(Criterion.all(self.get_conditions()))
        )

    def get_conditions(self):
        conditions = []

        conditions.append(self.gl_entry.is_cancelled == 0)
        conditions.append(self.gl_entry.voucher_type == "Payment Entry")
        conditions.append(self.gl_entry.company == self.filters.get("company"))
        conditions.append(self.gl_entry.account.isin(self.gst_accounts))

        if self.filters.get("customer"):
            conditions.append(self.gl_entry.party == self.filters.get("customer"))

        if self.filters.get("account"):
            conditions.append(self.pe.paid_from == self.filters.get("account"))

        if self.filters.get("show_for_period") and self.filters.get("from_date"):
            conditions.append(
                self.gl_entry.posting_date >= getdate(self.filters.get("from_date"))
            )
        else:
            conditions.append(IfNull(self.pe.unallocated_amount, 0) > 0)

        if self.filters.get("to_date"):
            conditions.append(
                self.gl_entry.posting_date <= getdate(self.filters.get("to_date"))
            )

        return conditions


def get_gst_accounts(filters):
    gst_accounts = get_gst_accounts_by_type(filters.get("company"), "Output")

    if not gst_accounts:
        return []

    return [account_head for account_head in gst_accounts.values() if account_head]
