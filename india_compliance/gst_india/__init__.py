import frappe

from frappe.utils.password import get_decrypted_password


@frappe.whitelist()
def get_gst_api_secret():
    if "System Manager" not in frappe.get_roles():
        return

    # TODO: validate key with apiman?
    return get_decrypted_password(
        "GST Settings", "GST Settings", "api_secret", raise_exception=False
    )
