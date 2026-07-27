import frappe
from frappe.query_builder.functions import IfNull


def execute():
    """
    Backfill `is_generated_with_ship_to` in e-Invoice Log.

    Only invoices with an IRN but no e-Waybill yet are relevant: ship-to sent during
    IRN generation cannot be replaced at e-Waybill generation (NIC error 2324), so the
    shipping address must stay locked until the e-Waybill is generated.
    """
    log = frappe.qb.DocType("e-Invoice Log")
    si = frappe.qb.DocType("Sales Invoice")

    # e-Invoice Log is named after the IRN
    irns_generated_with_ship_to = (
        frappe.qb.from_(si)
        .select(si.irn)
        .where(IfNull(si.irn, "") != "")
        .where(IfNull(si.ewaybill, "") == "")
        .where(IfNull(si.shipping_address_name, "") != "")
        .where(si.shipping_address_name != IfNull(si.customer_address, ""))
    )

    (
        frappe.qb.update(log)
        .set(log.is_generated_with_ship_to, 1)
        .where(log.name.isin(irns_generated_with_ship_to))
    ).run()
