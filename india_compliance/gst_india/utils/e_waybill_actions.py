"""e-Waybill state for the form, and what can still be done with a generated e-Waybill."""

import frappe
from frappe.utils import add_days, add_to_date, get_datetime

from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.e_waybill_applicability import get_e_waybill_applicability


def set_e_waybill_onload(doc, method=None):
    for key in ("e_waybill_info", "e_waybill_applicability"):
        doc.get_onload().pop(key, None)

    # applicability only matters until the e-Waybill is generated
    if doc.get("ewaybill"):
        if is_e_waybill_info_enabled() and (e_waybill_info := get_e_waybill_info(doc)):
            doc.set_onload("e_waybill_info", e_waybill_info)

        return

    e_waybill_applicability = get_e_waybill_applicability(doc)

    # the client reads a missing key as all flags off
    if not e_waybill_applicability.is_enabled():
        return

    doc.set_onload("e_waybill_applicability", e_waybill_applicability.get())


def is_e_waybill_info_enabled():
    gst_settings = frappe.get_cached_doc("GST Settings")

    # the doctype switch governs new e-Waybills; an existing one stays manageable
    return bool(gst_settings.enable_e_waybill and is_api_enabled(gst_settings))


def is_e_waybill_auto_cancellable(doc, e_waybill_info=None):
    if not (doc.get("ewaybill") and is_e_waybill_info_enabled()):
        return False

    e_waybill_info = e_waybill_info or doc.get_onload().get("e_waybill_info") or {}

    return bool(frappe.get_cached_doc("GST Settings").auto_cancel_e_waybill) and is_e_waybill_cancellable(
        e_waybill_info
    )


def is_e_waybill_cancellable(e_waybill_info):
    cancel_upto = e_waybill_info.get("cancel_upto")
    return bool(cancel_upto) and get_datetime(cancel_upto) >= get_datetime()


def is_e_waybill_updatable(e_waybill_info):
    # Part A alone has no validity yet
    valid_upto = e_waybill_info.get("valid_upto")
    return not valid_upto or get_datetime(valid_upto) >= get_datetime()


def is_e_waybill_extendable(e_waybill_info):
    # extendable until 8 hours after expiry; before that window it can be scheduled
    extend_before = e_waybill_info.get("extend_before")
    return bool(extend_before) and get_datetime(extend_before) >= get_datetime()


def is_e_waybill_extendable_now(e_waybill_info):
    extend_after = e_waybill_info.get("extend_after")
    return bool(extend_after) and get_datetime(extend_after) <= get_datetime() <= get_datetime(
        e_waybill_info.get("extend_before")
    )


def get_e_waybill_info(doc):
    e_waybill_info = frappe.db.get_value(
        "e-Waybill Log",
        doc.ewaybill,
        (
            "created_on",
            "valid_upto",
            "is_generated_in_sandbox_mode",
            "extension_scheduled",
        ),
        as_dict=True,
    )

    if not e_waybill_info:
        return

    created_on, valid_upto = e_waybill_info.created_on, e_waybill_info.valid_upto
    e_waybill_info.update(
        # the portal allows cancelling for 24 hours after generation
        cancel_upto=created_on and add_days(created_on, 1),
        # the portal extends only within 8 hours either side of expiry
        extend_after=valid_upto and add_to_date(valid_upto, hours=-8),
        extend_before=valid_upto and add_to_date(valid_upto, hours=8),
    )

    return e_waybill_info
