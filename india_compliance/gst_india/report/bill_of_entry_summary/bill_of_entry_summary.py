# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _

def execute(filters=None):
    validate_filters(filters)
    if not filters:
        filters = {}

    columns, data = get_columns(), get_data(filters)
    return columns, data


def validate_filters(filters=None):
    if filters is None:
        filters = {}
    filters = frappe._dict(filters)

    if not filters.company:
        frappe.throw(
            _("{} is mandatory for generating Bill of Entry Summary Report").format(
                _("Company")
            ),
            title=_("Invalid Filter"),
        )
    if not filters.from_date or not filters.to_date:
        frappe.throw(
            _(
                "From Date & To Date is mandatory for generating e-Invoice Summary"
                " Report"
            ),
            title=_("Invalid Filter"),
        )
    if filters.from_date > filters.to_date:
        frappe.throw(_("From Date must be before To Date"), title=_("Invalid Filter"))


def get_data(filters):
    data = get_boe_data(filters)
    return data


def get_boe_data(filters):
    bill_of_entry = frappe.qb.DocType("Bill of Entry")
    jea = frappe.qb.DocType("Journal Entry Account")

    query = (
        frappe.qb.from_(bill_of_entry)
        .left_join(jea)
        .on(bill_of_entry.name == jea.reference_name)
        .select(
            bill_of_entry.name,
            bill_of_entry.purchase_invoice,
            bill_of_entry.bill_of_entry_no,
            bill_of_entry.bill_of_entry_date,
            bill_of_entry.bill_of_lading_no,
            (bill_of_entry.total_taxable_value - bill_of_entry.total_customs_duty).as_(
                "total_assessable_value"
            ),
            bill_of_entry.total_customs_duty,
            bill_of_entry.total_taxes,
            bill_of_entry.total_amount_payable,
            jea.parent.as_("parent_journal_entry"),
        )
        .where(bill_of_entry.docstatus == 1)
        .where(
            bill_of_entry.bill_of_entry_date[
                filters.get("from_date") : filters.get("to_date")
            ]
        )
        .where(bill_of_entry.company == filters.get("company"))
    )

    query = update_purchase_invoice_query(query)
    boe_query = query.run(as_dict=1)
    return boe_query


def update_purchase_invoice_query(query):
    purchase_invoice = frappe.qb.DocType("Purchase Invoice")
    bill_of_entry = frappe.qb.DocType("Bill of Entry")

    return query.left_join(purchase_invoice).on(
        purchase_invoice.name == bill_of_entry.purchase_invoice
    ).select(
        purchase_invoice.supplier,
    )


def get_columns():
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
            "fieldtype": "Link",
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
            "fieldname": "parent_journal_entry",
            "label": _("Journal Entry for Payment"),
            "fieldtype": "Link",
            "options": "Journal Entry",
            "width": 100,
        },
        {
            "fieldname": "total_assessable_value",
            "label": _("Total Assessable Value"),
            "fieldtype": "Currency",
            "width": 110,
        },
        {
            "fieldname": "total_customs_duty",
            "label": _("Total Customs Duty"),
            "fieldtype": "Currency",
            "width": 110,
        },
        {
            "fieldname": "total_taxes",
            "label": _("Total Taxes"),
            "fieldtype": "Currency",
            "width": 100,
        },
        {
            "fieldname": "total_amount_payable",
            "label": _("Amount Payable"),
            "fieldtype": "Currency",
            "width": 90,
        },
    ]