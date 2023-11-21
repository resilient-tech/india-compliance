import frappe
import frappe.defaults
from frappe.utils.user import get_users_with_role


def execute():
    # All companies in India where PAN is of a registered company or is not set
    notification_required = frappe.get_all(
        "Company",
        filters={"country": "India"},
        or_filters=(
            ("pan", "like", "___C%"),
            ("pan", "is", "not set"),
        ),
        limit=1,
    )

    if not notification_required:
        return

    for user in get_users_with_role("Accounts Manager"):
        frappe.defaults.set_user_default("needs_audit_trail_notification", 1, user=user)
