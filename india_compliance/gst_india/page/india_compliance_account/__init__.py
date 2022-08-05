import json
import random

import frappe
from frappe.utils.password import get_decrypted_password, set_encrypted_password


@frappe.whitelist()
def get_api_secret():
    frappe.only_for("System Manager")

    return get_decrypted_password(
        "GST Settings",
        "GST Settings",
        fieldname="api_secret",
        raise_exception=False,
    )


@frappe.whitelist()
def set_api_secret(api_secret: str):
    frappe.only_for("System Manager")

    set_encrypted_password(
        "GST Settings", "GST Settings", api_secret, fieldname="api_secret"
    )
    frappe.db.set_value("GST Settings", None, "api_secret", "*" * random.randint(8, 16))
    _set_auth_session(None)


@frappe.whitelist()
def get_auth_session():
    frappe.only_for("System Manager")

    session = frappe.db.get_global("ic_auth_session")
    return session and json.loads(session)


@frappe.whitelist()
def set_auth_session(session: str = None):
    frappe.only_for("System Manager")

    if not session:
        return _set_auth_session(None)

    if not isinstance(session, str):
        session = json.dumps(session)

    return _set_auth_session(session)


def _set_auth_session(session):
    frappe.db.set_global("ic_auth_session", session)
