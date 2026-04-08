import frappe

from india_compliance.gst_india.constants import SERVICE_HSN_PREFIX, TAX_TYPES


def execute():
    """
    - For SEZ import invoices with goods items, set itc_classification to "Import Of Goods"
    - For BOE invoices, pending_boe_qty should be equal to qty
    - If single item is goods and rest are services, then also itc_classification should be "Import Of Goods".
    """
    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")
    pi_tax = frappe.qb.DocType("Purchase Taxes and Charges")

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
        .distinct()
    )

    # Set itc_classification to "Import Of Goods" for SEZ invoices with goods items
    (
        frappe.qb.update(pi)
        .set(pi.itc_classification, "Import Of Goods")
        .where(pi.docstatus == 1)
        .where(pi.gst_category == "SEZ")
        .where(pi.itc_classification != "Import Of Goods")
        .where(pi.name.isin(sez_invoices_with_goods))
        .run()
    )

    # For BOE invoices without taxes, pending_boe_qty should be equal to qty
    invoices_with_gst_taxes = (
        frappe.qb.from_(pi_tax)
        .select(pi_tax.parent)
        .where(pi_tax.parenttype == "Purchase Invoice")
        .where(pi_tax.gst_tax_type.isin(TAX_TYPES))
        .distinct()
    )
    (
        frappe.qb.update(pi_item)
        .set(pi_item.pending_boe_qty, pi_item.qty)
        .where(pi_item.parent.isin(sez_invoices_with_goods))
        .where(pi_item.parent.notin(invoices_with_gst_taxes))
        .run()
    )

    # For non-BOE sez invoice items with taxes, pending_boe_qty should be 0
    (
        frappe.qb.update(pi_item)
        .join(pi)
        .on(pi_item.parent == pi.name)
        .set(pi_item.pending_boe_qty, 0)
        .where(pi.docstatus == 1)
        .where(pi.gst_category == "SEZ")
        .where(pi.name.isin(invoices_with_gst_taxes))
        .run()
    )
