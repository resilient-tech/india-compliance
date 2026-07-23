import frappe

IMPORT_CLASSIFICATIONS = ("Import Of Goods", "Import Of Service")


def execute():
    """
    For existing import transactions (Import Of Goods or Import Of Service), set gst_treatment to "Taxable".
    """
    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")

    import_invoices = (
        frappe.qb.from_(pi)
        .select(pi.name)
        .where(pi.itc_classification.isin(IMPORT_CLASSIFICATIONS))
        .where(pi.docstatus == 1)
    )

    (
        frappe.qb.update(pi_item)
        .set(pi_item.gst_treatment, "Taxable")
        .where(pi_item.parent.isin(import_invoices))
        .where(pi_item.gst_treatment != "Taxable")
        .run()
    )
