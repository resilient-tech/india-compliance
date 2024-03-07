import frappe
from frappe.query_builder.functions import IfNull

from india_compliance.gst_india.doctype.gst_settings.gst_settings import (
    update_e_invoice_status,
)


def execute():
    update_e_invoice_status()
    set_pending_cancellation_status()


def set_pending_cancellation_status():
    sales_invoice = frappe.qb.DocType("Sales Invoice")

    (
        frappe.qb.update(sales_invoice)
        .set("einvoice_status", "Pending Cancellation")
        .where((sales_invoice.docstatus == 2) & (IfNull(sales_invoice.irn, "") != ""))
        .run()
    )
