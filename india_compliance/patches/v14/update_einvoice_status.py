import frappe

CHUNK_SIZE = 100000


def execute():
    doctype = "Sales Invoice"
    filters = {
        "docstatus": ["!=", 0],
        "einvoice_status": ["is", "not set"],
        "irn": ["is", "not set"],
    }
    query = (
        frappe.qb.get_query(
            doctype, filters=filters, update=True, validate_filters=True
        )
        .limit(CHUNK_SIZE)
        .set("e_invoice_status", "Not Applicable")
    )

    while frappe.db.exists(doctype, filters):
        query.run()
        frappe.db.commit()
