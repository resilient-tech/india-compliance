import json

import frappe
from frappe.utils.password import get_decrypted_password


@frappe.whitelist()
def get_gst_api_secret():
    frappe.only_for("System Manager")
    return get_decrypted_password(
        "GST Settings", "GST Settings", "api_secret", raise_exception=False
    )


@frappe.whitelist()
def set_gst_api_secret(api_secret):
    frappe.only_for("System Manager")
    frappe.set_value("GST Settings", None, "api_secret", api_secret)
    set_session(None)


@frappe.whitelist()
def get_session():
    frappe.only_for("System Manager")
    session = frappe.db.get_global("gst_auth_session")
    return session and json.loads(session)


@frappe.whitelist()
def set_session(session):
    frappe.only_for("System Manager")
    frappe.db.set_global("gst_auth_session", session)
