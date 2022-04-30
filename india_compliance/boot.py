import frappe


def set_bootinfo(bootinfo):
    gst_settings = frappe.get_cached_doc("GST Settings").as_dict()
    for key in ("api_secret", "gst_accounts", "credentials"):
        gst_settings.pop(key, None)

    bootinfo["gst_settings"] = gst_settings
