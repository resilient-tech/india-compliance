import frappe


def execute():
    template_name = "e-Invoice QR Code"
    if frappe.db.exists(
        "Web Template Field",
        {"parent": template_name, "fieldname": "e_invoice_qr_text"},
    ):
        frappe.db.delete("Web Template", template_name)
