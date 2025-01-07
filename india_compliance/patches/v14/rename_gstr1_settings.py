import frappe


def execute():
    settings = frappe.get_cached_doc("GST Settings")
    if not settings.compare_gstr_1_data:
        return

    frappe.db.set_value(
        "GST Settings", None, {"enable_gstr_1_api": 1, "compare_unfiled_data": 1}
    )
