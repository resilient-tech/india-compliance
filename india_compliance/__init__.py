import frappe
from frappe.utils.modules import get_modules_from_all_apps_for_user
from frappe.utils.user import is_website_user

__version__ = "17.0.0-dev"


def check_app_permission():
    if frappe.session.user == "Administrator":
        return True

    if is_website_user():
        return False

    allowed_modules = {m["module_name"] for m in get_modules_from_all_apps_for_user()}
    app_modules = frappe.get_module_list("india_compliance")

    return any(module in allowed_modules for module in app_modules)
