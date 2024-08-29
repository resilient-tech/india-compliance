import frappe
import frappe.defaults
from frappe.utils.user import get_users_with_role


def execute():
    if not frappe.db.exists("Company", {"country": "India"}):
        return

    # Users affected by creation of new GST category
    if not frappe.db.exists(
        "Purchase Invoice", {"itc_classification": "Input Service Distributor"}
    ):
        return

    for user in get_users_with_role("Accounts Manager"):
        frappe.defaults.set_user_default(
            "needs_new_gst_category_notification", 1, user=user
        )
