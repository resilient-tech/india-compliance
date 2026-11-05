# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import GroupConcat, Max, Sum
from frappe.utils import flt


def execute(filters=None):
    validate_filters(filters)
    if not filters:
        filters = {}

    data = get_data(filters)
    tax_accounts = set_tax_amounts(data)

    return get_columns(filters, tax_accounts), data


def validate_filters(filters=None):
    if filters is None:
        filters = {}
    filters = frappe._dict(filters)

    if not filters.company:
        frappe.throw(
            _("{} is mandatory for generating Bill of Entry Summary Report").format(_("Company")),
            title=_("Invalid Filter"),
        )
    if not filters.from_date or not filters.to_date:
        frappe.throw(
            _("From Date & To Date is mandatory for generating Bill of Entry Summary Report"),
            title=_("Invalid Filter"),
        )
    if filters.from_date > filters.to_date:
        frappe.throw(_("From Date must be before To Date"), title=_("Invalid Filter"))


def get_data(filters):
    bill_of_entry = frappe.qb.DocType("Bill of Entry")

    query = (
        frappe.qb.from_(bill_of_entry)
        .select(
            bill_of_entry.name,
            bill_of_entry.bill_of_entry_no,
            bill_of_entry.bill_of_entry_date,
            bill_of_entry.bill_of_lading_no,
            (bill_of_entry.total_taxable_value - bill_of_entry.total_customs_duty).as_(
                "total_assessable_value"
            ),
            bill_of_entry.total_customs_duty,
            bill_of_entry.total_taxes,
            bill_of_entry.total_amount_payable,
        )
        .where(bill_of_entry.docstatus == 1)
        .where(bill_of_entry.bill_of_entry_date[filters.get("from_date") : filters.get("to_date")])
        .where(bill_of_entry.company == filters.get("company"))
    )

    query = update_journal_entry_for_payment(query)
    query = update_purchase_invoice_query(query)
    data = query.run(as_dict=1)

    for row in data:
        for fieldname in ("payment_journal_entry", "purchase_invoice"):
            if row[fieldname]:
                row[fieldname] = ",".join(sorted(row[fieldname].split(",")))

    return data


def update_journal_entry_for_payment(query):
    bill_of_entry = frappe.qb.DocType("Bill of Entry")
    journal_entry_account = frappe.qb.DocType("Journal Entry Account")

    return (
        query.left_join(journal_entry_account)
        .on(
            (bill_of_entry.name == journal_entry_account.reference_name)
            & (journal_entry_account.reference_type == "Bill of Entry")
            & (journal_entry_account.docstatus == 1)
        )
        .select(GroupConcat(journal_entry_account.parent, ",").distinct().as_("payment_journal_entry"))
    )


def update_purchase_invoice_query(query):
    bill_of_entry = frappe.qb.DocType("Bill of Entry")
    bill_of_entry_item = frappe.qb.DocType("Bill of Entry Item")
    purchase_invoice = frappe.qb.DocType("Purchase Invoice")

    return (
        query.join(bill_of_entry_item)
        .on(bill_of_entry_item.parent == bill_of_entry.name)
        .left_join(purchase_invoice)
        .on(purchase_invoice.name == bill_of_entry_item.purchase_invoice)
        .select(
            GroupConcat(purchase_invoice.name, ",").distinct().as_("purchase_invoice"),
            Max(purchase_invoice.supplier).as_("supplier"),
        )
        .groupby(bill_of_entry.name)
    )


def set_tax_amounts(data):
    if not data:
        return []

    taxes = frappe.qb.DocType("India Compliance Taxes and Charges")
    tax_details = (
        frappe.qb.from_(taxes)
        .select(taxes.parent, taxes.account_head, taxes.gst_tax_type, Sum(taxes.tax_amount).as_("tax_amount"))
        .where(taxes.parenttype == "Bill of Entry")
        .where(taxes.parent.isin([row.name for row in data]))
        .groupby(taxes.parent, taxes.account_head, taxes.gst_tax_type)
        .run(as_dict=True)
    )

    rows = {row.name: row for row in data}
    gst_accounts = set()
    other_accounts = set()

    for detail in tax_details:
        if not detail.tax_amount:
            continue

        row = rows[detail.parent]
        row[detail.account_head] = flt(row.get(detail.account_head)) + detail.tax_amount
        (gst_accounts if detail.gst_tax_type else other_accounts).add(detail.account_head)

    return [*sorted(gst_accounts, key=str.lower), *sorted(other_accounts - gst_accounts, key=str.lower)]


def get_columns(filters, tax_accounts):
    company_currency = frappe.get_cached_value("Company", filters.get("company"), "default_currency")

    return [
        {
            "fieldname": "supplier",
            "label": _("Supplier"),
            "fieldtype": "Link",
            "options": "Supplier",
            "width": 100,
        },
        {
            "fieldname": "name",
            "label": _("Bill of Entry"),
            "fieldtype": "Link",
            "options": "Bill of Entry",
            "width": 140,
        },
        {
            "fieldname": "purchase_invoice",
            "label": _("Purchase Invoice"),
            "fieldtype": "Data",
            "options": "Purchase Invoice",
            "width": 130,
        },
        {
            "fieldname": "bill_of_entry_no",
            "label": _("BOE No."),
            "fieldtype": "Link",
            "options": "Bill of Entry",
            "width": 80,
        },
        {
            "fieldname": "bill_of_entry_date",
            "label": _("BOE Date"),
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "fieldname": "bill_of_lading_no",
            "label": _("Bill of Lading No."),
            "fieldtype": "Data",
            "width": 80,
        },
        {
            "fieldname": "payment_journal_entry",
            "label": _("Journal Entry for Payment"),
            "fieldtype": "Data",
            "options": "Journal Entry",
            "width": 100,
        },
        {
            "fieldname": "total_assessable_value",
            "label": _("Total Assessable Value"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 110,
        },
        {
            "fieldname": "total_customs_duty",
            "label": _("Total Customs Duty"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 110,
        },
        *[
            {
                "fieldname": account,
                "label": account,
                "fieldtype": "Currency",
                "options": company_currency,
                "width": 110,
            }
            for account in tax_accounts
        ],
        {
            "fieldname": "total_taxes",
            "label": _("Total Taxes and Charges"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 100,
        },
        {
            "fieldname": "total_amount_payable",
            "label": _("Amount Payable"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 90,
        },
    ]
