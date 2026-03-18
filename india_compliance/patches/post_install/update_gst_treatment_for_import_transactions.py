import frappe

IMPORT_CLASSIFICATIONS = ("Import Of Goods", "Import Of Service")


def execute():
    """
    For existing import transactions (Import Of Goods or Import Of Service), set gst_treatment to "Taxable".
    """
    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")

    (
        frappe.qb.update(pi_item)
        .inner_join(pi)
        .on(pi_item.parent == pi.name)
        .set(pi_item.gst_treatment, "Taxable")
        .where(pi.itc_classification.isin(IMPORT_CLASSIFICATIONS))
        .where(pi_item.gst_treatment != "Taxable")
        .where(pi.docstatus == 1)
        .run()
    )
