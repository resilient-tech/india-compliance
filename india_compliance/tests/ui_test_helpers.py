import frappe
from frappe.tests.utils import whitelist_for_tests

NOTIFICATION_KEYS = (
    "needs_audit_trail_notification",
    "needs_item_tax_template_notification",
    "needs_new_gst_category_notification",
)


@whitelist_for_tests(methods=["POST"])
def suppress_notifications():
    """Suppress notifications that would otherwise block the UI."""
    for key in NOTIFICATION_KEYS:
        frappe.defaults.clear_default(key)
        frappe.defaults.clear_user_default(key)

    return {"cleared": list(NOTIFICATION_KEYS)}


@whitelist_for_tests(methods=["POST"])
def set_gst_settings(**kwargs):
    """Set fields on the GST Settings single"""
    for field, value in kwargs.items():
        frappe.db.set_single_value("GST Settings", field, value)

    frappe.clear_cache()

    return kwargs


@whitelist_for_tests(methods=["POST"])
def delete_documents(doctype: str, names: str | list):
    """Cancel-then-delete the named documents"""
    names = frappe.parse_json(names) if isinstance(names, str) else names

    for name in names:
        doc = frappe.get_doc(doctype, name)
        if doc.docstatus == 1:
            doc.cancel()

        doc.delete(ignore_permissions=True)

    return names
