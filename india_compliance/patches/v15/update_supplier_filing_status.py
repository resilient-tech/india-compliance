import frappe


def execute():
    GSTR2 = frappe.qb.DocType("GST Inward Supply")
    (
        frappe.qb.update(GSTR2)
        .set("is_supplier_return_filed", 1)
        .where(GSTR2.gstr_1_filled == 1)
        .run()
    )
