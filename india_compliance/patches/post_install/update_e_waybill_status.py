import frappe
from frappe.query_builder.functions import IfNull
from frappe.utils import add_days, nowdate


def execute():
    # check if e-waybill is enabled
    e_waybill_enabled = frappe.db.get_value("Sales Invoice", {"ewaybill": ["is", "set"]})

    sales_invoice = frappe.qb.DocType("Sales Invoice")
    if not e_waybill_enabled:
        set_not_applicable_status(sales_invoice)
        return

    set_generated_status(sales_invoice)
    set_cancelled_status(sales_invoice)
    set_pending_status(sales_invoice)
    set_not_applicable_status(sales_invoice)


def set_generated_status(sales_invoice):
    (
        frappe.qb.update(sales_invoice)
        .set(sales_invoice.e_waybill_status, "Generated")
        .where(
            (sales_invoice.docstatus == 1)
            & (IfNull(sales_invoice.ewaybill, "") != "")
            & (IfNull(sales_invoice.e_waybill_status, "") == "")
            & (sales_invoice.is_opening != "Yes")
        )
        .run()
    )


def set_cancelled_status(sales_invoice):
    e_waybill_log = frappe.qb.DocType("e-Waybill Log")

    cancelled_e_waybills = (
        frappe.qb.from_(e_waybill_log)
        .select(e_waybill_log.reference_name)
        .where(e_waybill_log.is_cancelled == 1)
    )

    (
        frappe.qb.update(sales_invoice)
        .set(sales_invoice.e_waybill_status, "Cancelled")
        .where(
            sales_invoice.name.isin(cancelled_e_waybills)
            & (IfNull(sales_invoice.e_waybill_status, "") == "")
            & (IfNull(sales_invoice.ewaybill, "") == "")
            & (sales_invoice.is_opening != "Yes")
        )
        .run()
    )


def set_pending_status(sales_invoice):
    if not frappe.flags.in_install:
        e_waybill_applicable = frappe.db.get_single_value("GST Settings", "enable_e_waybill")

        if not e_waybill_applicable:
            return

    from_date = add_days(nowdate(), -30)
    e_waybill_threshold = frappe.db.get_single_value("GST Settings", "e_waybill_threshold")

    sales_invoice_item = frappe.qb.DocType("Sales Invoice Item")

    invoices_with_goods_item = (
        frappe.qb.from_(sales_invoice_item)
        .select(sales_invoice_item.parent)
        .where(
            (IfNull(sales_invoice_item.gst_hsn_code, "") != "")
            | (sales_invoice_item.gst_hsn_code.not_like("99%"))
        )
    )

    (
        frappe.qb.update(sales_invoice)
        .set(sales_invoice.e_waybill_status, "Pending")
        .where(
            (IfNull(sales_invoice.ewaybill, "") == "")
            & (IfNull(sales_invoice.e_waybill_status, "") == "")
            & (sales_invoice.docstatus == 1)
            & (sales_invoice.posting_date >= from_date)
            & (sales_invoice.base_grand_total >= e_waybill_threshold)
            & sales_invoice.name.isin(invoices_with_goods_item)
            & (sales_invoice.company_gstin != sales_invoice.billing_address_gstin)
            & (sales_invoice.is_return == 0)
            & (sales_invoice.is_debit_note == 0)
            & (sales_invoice.is_opening != "Yes")
        )
        .run()
    )


def set_not_applicable_status(sales_invoice):
    (
        frappe.qb.update(sales_invoice)
        .set(sales_invoice.e_waybill_status, "Not Applicable")
        .where(
            (sales_invoice.docstatus != 0)
            & (IfNull(sales_invoice.e_waybill_status, "") == "")
            & (IfNull(sales_invoice.ewaybill, "") == "")
        )
        .run()
    )
