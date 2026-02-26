import json
import random

import frappe
from frappe.utils.password import (
    get_decrypted_password,
    remove_encrypted_password,
    set_encrypted_password,
)

from india_compliance.gst_india.utils import has_permission_of_page

page_name = "india-compliance-account"


@frappe.whitelist()
def get_api_secret():
    has_permission_of_page(page_name, throw=True)

    return get_decrypted_password(
        "GST Settings",
        "GST Settings",
        fieldname="api_secret",
        raise_exception=False,
    )


@frappe.whitelist()
def set_api_secret(api_secret: str):
    has_permission_of_page(page_name, throw=True)

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
    has_permission_of_page(page_name, throw=True)

    session = frappe.db.get_global("ic_auth_session")
    return session and json.loads(session)


@frappe.whitelist()
def set_auth_session(session: str | None = None):
    has_permission_of_page(page_name, throw=True)

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
