import json
import random

import frappe
from frappe.utils.password import (
    get_decrypted_password,
    remove_encrypted_password,
    set_encrypted_password,
)


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

    if not api_secret:
        return logout()

    set_encrypted_password(
        "GST Settings", "GST Settings", api_secret, fieldname="api_secret"
    )
    frappe.db.set_single_value(
        "GST Settings", "api_secret", "*" * random.randint(8, 16)
    )
    post_login()


def post_login():
    _set_auth_session(None)
    _disable_api_promo()


def logout():
    remove_encrypted_password("GST Settings", "GST Settings", fieldname="api_secret")
    frappe.db.set_single_value("GST Settings", "api_secret", None)


@frappe.whitelist()
def get_auth_session():
    frappe.only_for("System Manager")

    session = frappe.db.get_global("ic_auth_session")
    return session and json.loads(session)


@frappe.whitelist()
def set_auth_session(session: str = None):
    frappe.only_for("System Manager")

    if not session:
        _set_auth_session(None)
        return

    if not isinstance(session, str):
        session = json.dumps(session)

    _set_auth_session(session)


def _set_auth_session(session):
    frappe.db.set_global("ic_auth_session", session)


def _disable_api_promo():
    frappe.db.set_global("ic_api_promo_dismissed", 1)
