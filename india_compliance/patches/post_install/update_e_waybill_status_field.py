import frappe
from frappe.utils import add_days, nowdate


def execute():
    # check if e-waybill is enabled
    if not frappe.db.get_value(
        "Sales Invoice",
        {"ewaybill": ["is", "set"]},
    ):
        return

    e_waybill_threshold = frappe.db.get_single_value(
        "GST Settings", "e_waybill_threshold"
    )

    set_generated_status()
    set_cancelled_status()
    set_pending_status(e_waybill_threshold)
    set_not_applicable_status()


def set_generated_status():
    frappe.db.set_value(
        "Sales Invoice",
        {"ewaybill": ["is", "set"]},
        "ewaybill_status",
        "Generated",
    )


def set_cancelled_status():
    sales_invoice = frappe.qb.DocType("Sales Invoice")
    e_waybill_log = frappe.qb.DocType("e-Waybill Log")

    frappe.qb.update(sales_invoice).join(e_waybill_log).on(
        sales_invoice.name == e_waybill_log.reference_name
    ).set(sales_invoice.e_waybill_status, "Cancelled").where(
        ((sales_invoice.ewaybill == "") | (sales_invoice.ewaybill.isnull()))
        & (e_waybill_log.is_cancelled == 1)
    ).run()


def set_pending_status(ewaybill_threshold):
    old_invoice_date = add_days(nowdate(), -30)
    sales_invoice = frappe.qb.DocType("Sales Invoice")
    sales_invoice_item = frappe.qb.DocType("Sales Invoice Item")

    frappe.qb.update(sales_invoice).join(sales_invoice_item).on(
        sales_invoice.name == sales_invoice_item.parent
    ).set(sales_invoice.e_waybill_status, "Pending").where(
        (sales_invoice.ewaybill == "")
        & (sales_invoice.docstatus == 1)
        & (sales_invoice.posting_date >= old_invoice_date)
        & (sales_invoice.base_grand_total >= ewaybill_threshold)
        & (
            (sales_invoice_item.gst_hsn_code != "")
            | (sales_invoice_item.gst_hsn_code.isnull())
            | (sales_invoice_item.gst_hsn_code.not_like("99%"))
        )
        & (sales_invoice.company_gstin != sales_invoice.billing_address_gstin)
        & (sales_invoice.is_return == 0)
        & (sales_invoice.is_debit_note == 0)
    ).run()


def set_not_applicable_status():
    frappe.db.set_value(
        "Sales Invoice",
        {
            "e_waybill_status": ["is", "not set"],
            "ewaybill": ["is", "not set"],
            "docstatus": 1,
        },
        "e_waybill_status",
        "Not Applicable",
    )
