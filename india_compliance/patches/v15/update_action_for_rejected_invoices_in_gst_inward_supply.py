import frappe
from frappe.query_builder import Case


def execute():
    """
    Update the action for invoices where ims_action is "Rejected"
    1. If invoice is "Rejected" then mark action as "Ignore" only if no action is taken on invoice.
    2. Copy current action to previous action irrespective of ims_action.
    """
    GSTR2 = frappe.qb.DocType("GST Inward Supply")

    (
        frappe.qb.update(GSTR2)
        .set("previous_action", GSTR2.action)
        .set(
            "action",
            Case().when(GSTR2.action == "No Action", "Ignore").else_(GSTR2.action),
        )
        .where(GSTR2.ims_action == "Rejected")
        .run()
    )
