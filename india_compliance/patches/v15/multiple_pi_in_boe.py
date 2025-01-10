import frappe
from frappe.model.document import bulk_insert


def execute():
    boe = frappe.qb.DocType("Bill of Entry", alias="boe")
    boe_item = frappe.qb.DocType("Bill of Entry Item", alias="boe_item")

    # link BOE item to it's purchase invoice
    (
        frappe.qb.update(boe_item)
        .join(boe)
        .on(boe_item.parent == boe.name)
        .set(boe_item.purchase_invoice, boe.purchase_invoice)
        .run(as_dict=True)
    )

    add_purchase_invoices()


def add_purchase_invoices():
    bill_of_entry = frappe.get_all(
        "Bill of Entry",
        fields=["name", "purchase_invoice"],
    )

    linked_purchase_invoices = {
        boe["purchase_invoice"] for boe in bill_of_entry if boe["purchase_invoice"]
    }
    if not linked_purchase_invoices:
        return

    purchase_invoices = frappe.get_all(
        "Purchase Invoice",
        filters={"name": ["in", list(linked_purchase_invoices)]},
        fields=["name", "supplier", "posting_date", "grand_total"],
    )
    purchase_invoice_map = {pi["name"]: pi for pi in purchase_invoices}

    boe_pi_docs = get_records_to_insert(bill_of_entry, purchase_invoice_map)

    bulk_insert("BOE Purchase Invoice", boe_pi_docs, ignore_duplicates=True)


def get_records_to_insert(bill_of_entry, purchase_invoice_map):
    boe_pi = []
    for boe in bill_of_entry:
        pi = purchase_invoice_map.get(boe.purchase_invoice)
        if not pi:
            continue

        boe_pi_doc = frappe.get_doc(
            {
                "doctype": "BOE Purchase Invoice",
                "purchase_invoice": boe.purchase_invoice,
                "supplier": pi.supplier,
                "posting_date": pi.posting_date,
                "grand_total": pi.grand_total,
                "parent": boe.name,
                "parentfield": "purchase_invoices",
                "parenttype": "Bill of Entry",
            }
        )
        boe_pi_doc.set_new_name()
        boe_pi.append(boe_pi_doc)

    return boe_pi
