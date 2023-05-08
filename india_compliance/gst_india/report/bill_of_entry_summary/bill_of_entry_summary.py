# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
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


def get_boe_data(filters):
    pi = frappe.qb.DocType("Purchase Invoice")
    boe = frappe.qb.DocType("Bill of Entry")
    jv_par = frappe.qb.DocType("Journal Entry")
    jv = frappe.qb.DocType("Journal Entry Account")

    query = (
        frappe.qb.from_(boe)
        .inner_join(pi)
        .on(pi.name == boe.purchase_invoice)
        .left_join(jv)
        .on(jv.reference_name == boe.name)
        .left_join(jv_par)
        .on(jv_par.name == jv.parent)
        .select(
            boe.name,
            boe.bill_of_entry_no,
            boe.bill_of_entry_date,
            boe.purchase_invoice,
            boe.bill_of_lading_no,
            pi.supplier,
            pi.posting_date,
            pi.grand_total,
            boe.total_taxable_value,
            boe.total_customs_duty,
            (boe.total_taxable_value - boe.total_customs_duty).as_(
                "total_assessable_value"
            ),
            boe.total_taxes,
            boe.total_amount_payable,
            jv_par.name.as_("parent_journal_entry"),
        )
        .where(boe.docstatus == 1)
        .where(
            boe.bill_of_entry_date[filters.get("from_date") : filters.get("to_date")]
        )
        .where(pi.company == filters.get("company"))
    )

    boe_query = query.run(as_dict=True)
    return boe_query