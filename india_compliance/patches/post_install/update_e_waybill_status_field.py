import frappe
from frappe.utils import add_days, nowdate

CHUNK_SIZE = 100000


def execute():
    # check if e-waybill is enabled
    e_waybill_enabled = frappe.db.get_value(
        "Sales Invoice", {"ewaybill": ["is", "set"]}
    )

    if not e_waybill_enabled:
        set_not_applicable_status()
        return

    set_generated_status()
    set_cancelled_status()
    set_pending_status()
    set_not_applicable_status()


def set_generated_status():
    filters = {
        "ewaybill": ["is", "set"],
        "docstatus": 1,
        "e_waybill_status": ["is", "not set"],
    }
    update_e_waybill_status(filters, "Generated")


def set_cancelled_status():
    sales_invoice = frappe.qb.DocType("Sales Invoice")
    e_waybill_log = frappe.qb.DocType("e-Waybill Log")

    cancelled_invoice = (
        frappe.qb.from_(sales_invoice)
        .join(e_waybill_log)
        .on(sales_invoice.name == e_waybill_log.reference_name)
        .select(sales_invoice.name)
        .where(
            ((sales_invoice.ewaybill == "") | (sales_invoice.ewaybill.isnull()))
            & (e_waybill_log.is_cancelled == 1)
            & (sales_invoice.e_waybill_status.isnull())
        )
        .run()
    )

    cancelled_invoice = [item[0] for item in cancelled_invoice]

    filters = {
        "name": ["in", cancelled_invoice],
        "e_waybill_status": ["is", "not set"],
    }

    update_e_waybill_status(filters, "Cancelled")


def set_pending_status():
    if not frappe.flags.in_install:
        e_waybill_applicable = frappe.db.get_single_value(
            "GST Settings", "enable_e_waybill"
        )

        if not e_waybill_applicable:
            return

    from_date = add_days(nowdate(), -30)
    e_waybill_threshold = frappe.db.get_single_value(
        "GST Settings", "e_waybill_threshold"
    )

    sales_invoice = frappe.qb.DocType("Sales Invoice")
    sales_invoice_item = frappe.qb.DocType("Sales Invoice Item")

    frappe.qb.update(sales_invoice).join(sales_invoice_item).on(
        sales_invoice.name == sales_invoice_item.parent
    ).set(sales_invoice.e_waybill_status, "Pending").where(
        ((sales_invoice.ewaybill == "") | (sales_invoice.ewaybill.isnull()))
        & (sales_invoice.e_waybill_status.isnull())
        & (sales_invoice.docstatus == 1)
        & (sales_invoice.posting_date >= from_date)
        & (sales_invoice.base_grand_total >= e_waybill_threshold)
        & (
            (sales_invoice_item.gst_hsn_code != "")
            | (sales_invoice_item.gst_hsn_code.notnull())
            | (sales_invoice_item.gst_hsn_code.not_like("99%"))
        )
        & (sales_invoice.company_gstin != sales_invoice.billing_address_gstin)
        & (sales_invoice.is_return == 0)
        & (sales_invoice.is_debit_note == 0)
    ).run()


def set_not_applicable_status():
    filters = {
        "ewaybill": ["is", "not set"],
        "docstatus": ["!=", 0],
        "e_waybill_status": ["is", "not set"],
    }

    update_e_waybill_status(filters, "Not Applicable")


def update_e_waybill_status(filters, status):
    doctype = "Sales Invoice"
    query = (
        frappe.qb.get_query(
            doctype, filters=filters, update=True, validate_filters=True
        )
        .limit(CHUNK_SIZE)
        .set("e_waybill_status", status)
    )

    while frappe.db.exists(doctype, filters):
        query.run()
        frappe.db.commit()
