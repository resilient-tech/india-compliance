import frappe

from india_compliance.gst_india.utils.custom_fields import delete_old_fields


def execute():
    if not frappe.db.has_column("Payment Entry", "customer_gstin"):
        return

    payment_entry = frappe.qb.DocType("Payment Entry")
    frappe.qb.update(payment_entry).set(
        payment_entry.billing_address_gstin, payment_entry.customer_gstin
    ).run()

    delete_old_fields("customer_gstin", "Payment Entry")
