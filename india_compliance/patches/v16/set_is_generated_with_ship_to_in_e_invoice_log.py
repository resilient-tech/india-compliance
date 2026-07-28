import frappe


def execute():
    """
    Backfill `is_generated_with_ship_to` in e-Invoice Log.

    Ship To details sent during IRN generation can't be replaced while generating the
    e-Waybill by IRN (NIC error 2324).
    """
    e_invoice_log = frappe.qb.DocType("e-Invoice Log")

    (
        frappe.qb.update(e_invoice_log)
        .set(e_invoice_log.is_generated_with_ship_to, 1)
        .where(e_invoice_log.invoice_data.like("%ShipDtls%"))
    ).run()
