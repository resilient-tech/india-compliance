import frappe


def execute():
    if not frappe.db.has_column("Company Print Options", "autofield"):
        return

    doc = frappe.qb.DocType("Company Print Options")

    (
        frappe.qb.update(doc)
        .set(doc.print_label, doc.autofield)
        .set(doc.print_value, doc.autofield_value)
        .run()
    )
