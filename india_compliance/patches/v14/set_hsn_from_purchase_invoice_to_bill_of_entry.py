from pypika import AliasedQuery

import frappe
from frappe.query_builder.functions import IfNull


def execute():
    bill_of_entry = frappe.qb.DocType("Bill of Entry")
    bill_of_entry_item = frappe.qb.DocType("Bill of Entry Item")
    purchase_invoice_item = frappe.qb.DocType("Purchase Invoice Item")

    # using subquery to avoid ambiguous error for gst_hsn_code due to bug in pypika
    purchase_invoice_items = (
        frappe.qb.from_(purchase_invoice_item)
        .select(
            purchase_invoice_item.gst_hsn_code.as_("pur_hsn_code"),
            purchase_invoice_item.parent.as_("pur_name"),
            purchase_invoice_item.item_code.as_("pur_item"),
        )
        .where(IfNull(purchase_invoice_item.gst_hsn_code, "") != "")
        .where(purchase_invoice_item.docstatus == 1)
    )

    purchase_invoice_items = (
        frappe.qb.with_(purchase_invoice_items, "purchase_invoice_items")
        .from_(AliasedQuery("purchase_invoice_items"))
        .select("*")
    )

    (
        frappe.qb.update(bill_of_entry_item)
        .set(bill_of_entry_item.gst_hsn_code, purchase_invoice_items.pur_hsn_code)
        .join(bill_of_entry)
        .on(bill_of_entry_item.parent == bill_of_entry.name)
        .join(purchase_invoice_items)
        .on(purchase_invoice_items.pur_name == bill_of_entry.purchase_invoice)
        .where(purchase_invoice_items.pur_item == bill_of_entry_item.item_code)
        .where(bill_of_entry.docstatus == 1)
        .run()
    )
