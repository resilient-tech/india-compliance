# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
    validate_filters(filters)
    if not filters:
        filters = {}

    columns, data = get_columns(), get_data(filters)
    # if not data:
    #     frappe.throw("No data found for the given filters")
    return columns, data


def get_columns():
    return [
        {
            "fieldname": "supplier",
            "label": "Supplier",
            "fieldtype": "Link",
            "options": "Supplier",
            "width": 100,
        },
        {
            "fieldname": "name",
            "label": "Bill of Entry",
            "fieldtype": "Link",
            "options": "Bill of Entry",
            "width": 140,
        },
        {
            "fieldname": "purchase_invoice",
            "label": "Purchase Invoice",
            "fieldtype": "Link",
            "options": "Purchase Invoice",
            "width": 130,
        },
        {
            "fieldname": "bill_of_entry_no",
            "label": "BOE No.",
            "fieldtype": "Link",
            "options": "Bill of Entry",
            "width": 80,
        },
        {
            "fieldname": "bill_of_entry_date",
            "label": "BOE Date",
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "fieldname": "bill_of_lading_no",
            "label": "Bill of Lading No.",
            "fieldtype": "Data",
            "width": 80,
        },
        {
            "fieldname": "parent_journal_entry",
            "label": "Journal Entry for Payment",
            "fieldtype": "Link",
            "options": "Journal Entry",
            "width": 100,
        },
        {
            "fieldname": "total_assessable_value",
            "label": "Total Assessable Value",
            "fieldtype": "Currency",
            "width": 110,
        },
        {
            "fieldname": "total_customs_duty",
            "label": "Total Customs Duty",
            "fieldtype": "Currency",
            "width": 110,
        },
        {
            "fieldname": "total_taxes",
            "label": "Total Taxes",
            "fieldtype": "Currency",
            "width": 100,
        },
        {
            "fieldname": "total_amount_payable",
            "label": "Amount Payable",
            "fieldtype": "Currency",
            "width": 90,
        },
    ]


def get_data(filters):
    result = []
    boe_data = get_boe_data(filters)

    for boe in boe_data:
        row = {
            "supplier": boe.supplier,
            "name": boe.name,
            "purchase_invoice": boe.purchase_invoice,
            "bill_of_entry_no": boe.bill_of_entry_no,
            "bill_of_entry_date": boe.bill_of_entry_date,
            "bill_of_lading_no": boe.bill_of_lading_no,
            "parent_journal_entry": boe.parent_journal_entry,
            "total_assessable_value": boe.total_assessable_value,
            "total_customs_duty": boe.total_customs_duty,
            "total_taxes": boe.total_taxes,
            "total_amount_payable": boe.total_amount_payable,
        }
        result.append(row)

    return result


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


def get_boe_data(filters):
    purchase_invoice = frappe.qb.DocType("Purchase Invoice")
    bill_of_entry = frappe.qb.DocType("Bill of Entry")
    journal_entry = frappe.qb.DocType("Journal Entry")
    jea = frappe.qb.DocType("Journal Entry Account")

    query = (
        frappe.qb.from_(bill_of_entry)
        .inner_join(purchase_invoice)
        .on(purchase_invoice.name == bill_of_entry.purchase_invoice)
        .left_join(jea)
        .on(jea.reference_name == bill_of_entry.name)
        .left_join(journal_entry)
        .on(journal_entry.name == jea.parent)
        .select(
            bill_of_entry.name,
            bill_of_entry.bill_of_entry_no,
            bill_of_entry.bill_of_entry_date,
            bill_of_entry.purchase_invoice,
            bill_of_entry.bill_of_lading_no,
            purchase_invoice.supplier,
            purchase_invoice.posting_date,
            purchase_invoice.grand_total,
            bill_of_entry.total_taxable_value,
            bill_of_entry.total_customs_duty,
            (bill_of_entry.total_taxable_value - bill_of_entry.total_customs_duty).as_(
                "total_assessable_value"
            ),
            bill_of_entry.total_taxes,
            bill_of_entry.total_amount_payable,
            journal_entry.name.as_("parent_journal_entry"),
        )
        .where(bill_of_entry.docstatus == 1)
        .where(
            bill_of_entry.bill_of_entry_date[
                filters.get("from_date") : filters.get("to_date")
            ]
        )
        .where(purchase_invoice.company == filters.get("company"))
    )

    boe_query = query.run(as_dict=True)
    return boe_query
