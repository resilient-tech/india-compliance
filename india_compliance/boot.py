import frappe
import frappe.defaults
from frappe.utils import cint
from erpnext.stock.get_item_details import sales_doctypes

from india_compliance.audit_trail.utils import (
    enqueue_disable_audit_trail_notification,
    is_audit_trail_enabled,
)
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

    set_trigger_for_audit_trail_notification(bootinfo)


def set_trigger_for_audit_trail_notification(bootinfo):
    if not bootinfo.sysdefaults or not cint(
        bootinfo.sysdefaults.get("needs_audit_trail_notification", 0)
    ):
        return

    if is_audit_trail_enabled():
        enqueue_disable_audit_trail_notification()
        return

    bootinfo["needs_audit_trail_notification"] = True
