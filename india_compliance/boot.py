import frappe
from erpnext.stock.get_item_details import sales_doctypes

from india_compliance.gst_india.constants import STATE_NUMBERS


def set_bootinfo(bootinfo):
    bootinfo["sales_doctypes"] = sales_doctypes

    gst_settings = frappe.get_cached_doc("GST Settings").as_dict()
    for key in ("api_secret", "gst_accounts", "credentials"):
        gst_settings.pop(key, None)

    bootinfo["gst_settings"] = gst_settings
    bootinfo["india_state_options"] = list(STATE_NUMBERS)
