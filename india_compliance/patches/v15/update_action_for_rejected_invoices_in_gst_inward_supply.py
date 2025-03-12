import frappe
from frappe.query_builder.functions import IfNull


def execute():
    """
    Update the action for invoices where ims_action is "Rejected"
    1. If invoice is "Rejected" then mark action as "Ignore" only if invoice is not matched.
    2. And copy current action to previous action.
    """
    GSTR2 = frappe.qb.DocType("GST Inward Supply")

    (
        frappe.qb.update(GSTR2)
        .set("previous_action", GSTR2.action)
        .set("action", "Ignore")
        .where(GSTR2.ims_action == "Rejected")
        .where(IfNull(GSTR2.link_name, "") == "")
        .run()
    )
