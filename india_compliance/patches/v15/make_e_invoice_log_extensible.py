import frappe


def execute():
    e_invoice_log = frappe.qb.DocType("e-Invoice Log")

    frappe.qb.update(e_invoice_log).set(
        e_invoice_log.reference_name, e_invoice_log.sales_invoice
    ).set(e_invoice_log.reference_doctype, "Sales Invoice").run()
