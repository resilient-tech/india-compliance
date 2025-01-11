import frappe
from frappe.utils import sbool


def execute():
    settings = frappe.get_cached_doc("GST Settings")
    if not sbool(settings.get("compare_gstr_1_data")):
        return

    frappe.db.set_single_value(
        "GST Settings", {"enable_gstr_1_api": 1, "compare_unfiled_data": 1}
    )
