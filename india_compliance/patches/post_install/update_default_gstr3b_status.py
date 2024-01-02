import frappe


def execute():
    doc = frappe.qb.DocType("GSTR 3B Report")
    frappe.qb.update(doc).set(doc.generation_status, "Generated").where(
        doc.generation_status.isnull()
    ).run()
