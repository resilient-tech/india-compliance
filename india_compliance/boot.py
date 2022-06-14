import frappe

from india_compliance.gst_india.constants import STATE_NUMBERS


def set_bootinfo(bootinfo):
    gst_settings = frappe.get_cached_doc("GST Settings").as_dict()
    for key in ("api_secret", "gst_accounts", "credentials"):
        gst_settings.pop(key, None)

    bootinfo["gst_settings"] = gst_settings
    bootinfo["india_state_options"] = "\n".join(STATE_NUMBERS)
