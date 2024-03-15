import frappe


def execute():
    bill_of_entry = frappe.qb.DocType("Bill of Entry")
    bill_of_entry_item = frappe.qb.DocType("Bill of Entry Item")
    purchase_invoice_item = frappe.qb.DocType("Purchase Invoice Item")

    query = (
        frappe.qb.update(bill_of_entry_item)
        .set(bill_of_entry_item.gst_hsn_code, purchase_invoice_item.gst_hsn_code)
        .join(bill_of_entry)
        .on(bill_of_entry_item.parent == bill_of_entry.name)
        .join(purchase_invoice_item)
        .on(purchase_invoice_item.parent == bill_of_entry.purchase_invoice)
        .where(purchase_invoice_item.gst_hsn_code != "")
        .where(purchase_invoice_item.item_code == bill_of_entry_item.item_code)
    )

    print(query)
