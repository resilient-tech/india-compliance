import frappe

from india_compliance.gst_india.constants import SERVICE_HSN_PREFIX


def execute():
    """
    - For SEZ import invoices with goods items and no tax charged, set itc_classification to "Import Of Goods"
    - For BOE invoices, pending_boe_qty should be equal to qty
    - For non-BOE SEZ invoice items, pending_boe_qty should be 0.
    """
    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")

    sez_invoices_with_goods = (
        frappe.qb.from_(pi_item)
        .join(pi)
        .on(pi_item.parent == pi.name)
        .select(pi_item.parent)
        .where(pi.docstatus == 1)
        .where(pi.gst_category == "SEZ")
        .where(pi_item.qty != 0)
        .where(pi_item.gst_hsn_code != "")
        .where(pi_item.gst_hsn_code.not_like(f"{SERVICE_HSN_PREFIX}%"))
        .where((pi_item.igst_rate + pi_item.cgst_rate + pi_item.sgst_rate) == 0)
        .distinct()
    )

    # Set itc_classification to "Import Of Goods" for SEZ invoices with goods items and no tax charged
    (
        frappe.qb.update(pi)
        .set(pi.itc_classification, "Import Of Goods")
        .where(pi.docstatus == 1)
        .where(pi.gst_category == "SEZ")
        .where(pi.itc_classification != "Import Of Goods")
        .where(pi.name.isin(sez_invoices_with_goods))
        .run()
    )

    # For BOE invoices, pending_boe_qty should be equal to qty
    (
        frappe.qb.update(pi_item)
        .set(pi_item.pending_boe_qty, pi_item.qty)
        .where(pi_item.parent.isin(sez_invoices_with_goods))
        .run()
    )

    # For non-BOE sez invoice items, pending_boe_qty should be 0
    (
        frappe.qb.update(pi_item)
        .join(pi)
        .on(pi_item.parent == pi.name)
        .set(pi_item.pending_boe_qty, 0)
        .where(pi.docstatus == 1)
        .where(pi.gst_category == "SEZ")
        .where(pi.itc_classification != "Import Of Goods")
        .run()
    )
