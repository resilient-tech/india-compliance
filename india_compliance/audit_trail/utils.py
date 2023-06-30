import frappe
import frappe.defaults


def is_audit_trail_enabled():
    return bool(frappe.db.get_single_value("Accounts Settings", "enable_audit_trail"))


def get_audit_trail_doctypes():
    audit_trail_doctypes = []

    audit_trail_doctypes += frappe.get_hooks("erpnext_audit_trail_doctypes")
    audit_trail_doctypes += frappe.get_hooks("india_compliance_audit_trail_doctypes")

    if "lending" in frappe.get_installed_apps():
        audit_trail_doctypes += frappe.get_hooks("lending_audit_trail_doctypes")

    return set(audit_trail_doctypes)


def enqueue_disable_audit_trail_notification():
    frappe.enqueue(
        "india_compliance.audit_trail.utils.disable_audit_trail_notification",
        queue="short",
    )


@frappe.whitelist(methods=["POST"])
def disable_audit_trail_notification():
    frappe.defaults.clear_user_default("needs_audit_trail_notification")


@frappe.whitelist(methods=["POST"])
def enable_audit_trail():
    accounts_settings = frappe.get_doc("Accounts Settings")
    accounts_settings.enable_audit_trail = 1
    accounts_settings.flags.ignore_version = True
    accounts_settings.save()
