import frappe
from frappe.query_builder.functions import IfNull, Sum


def execute():
    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")
    boe_item = frappe.qb.DocType("Bill of Entry Item")

    submitted_boe_qty = (
        frappe.qb.from_(boe_item)
        .select(boe_item.pi_detail, Sum(boe_item.qty).as_("qty"))
        .where(boe_item.docstatus == 1)
        .groupby(boe_item.pi_detail)
    )

    (
        frappe.qb.update(pi_item)
        .join(pi)
        .on(pi_item.parent == pi.name)
        .left_join(submitted_boe_qty)
        .on(pi_item.name == submitted_boe_qty.pi_detail)
        .set(
            pi_item.pending_boe_qty,
            pi_item.qty - IfNull(submitted_boe_qty.qty, 0),
        )
        .where(pi.docstatus == 1)
        .where(pi.gst_category == "Overseas")
        .run()
    )
