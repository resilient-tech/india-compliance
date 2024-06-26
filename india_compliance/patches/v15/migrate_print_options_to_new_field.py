import frappe


def execute():
    doc = frappe.qb.DocType("Company Print Options")

    (
        frappe.qb.update(doc)
        .set(doc.print_label, doc.autofield)
        .set(doc.print_value, doc.autofield_value)
        .run()
    )
