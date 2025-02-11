import frappe
from frappe.utils.user import is_website_user

__version__ = "16.0.0-dev"


def check_app_permission():
    if frappe.session.user == "Administrator":
        return True

    if is_website_user():
        return False

    return True
