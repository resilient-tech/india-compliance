import frappe
from frappe.utils.modules import get_visible_modules
from frappe.utils.user import is_website_user

__version__ = "17.0.0-dev"


def check_app_permission():
    if frappe.session.user == "Administrator":
        return True

    if is_website_user():
        return False

    return bool(get_visible_modules(frappe.get_module_list("india_compliance")))
