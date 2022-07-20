import frappe
from erpnext.stock.get_item_details import sales_doctypes

from india_compliance.gst_india.constants import GST_PARTY_TYPES, STATE_NUMBERS


def set_bootinfo(bootinfo):
    bootinfo["sales_doctypes"] = sales_doctypes
    bootinfo["gst_party_types"] = GST_PARTY_TYPES

    gst_settings = frappe.get_cached_doc("GST Settings").as_dict()
    gst_settings.api_secret = "***" if gst_settings.api_secret else ""

    for key in ("gst_accounts", "credentials"):
        gst_settings.pop(key, None)

    bootinfo["gst_settings"] = gst_settings
    bootinfo["india_state_options"] = list(STATE_NUMBERS)
    bootinfo["ic_api_enabled_from_conf"] = bool(frappe.conf.ic_api_secret)
