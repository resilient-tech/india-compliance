"""e-Waybill state for the form, and what can still be done with a generated e-Waybill."""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime

from india_compliance.gst_india.constants.e_waybill import PERMITTED_DOCTYPES
from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.e_waybill_applicability import get_e_waybill_applicability


def set_e_waybill_onload(doc, method=None):
    for key in ("e_waybill_info", "e_waybill_applicability"):
        doc.get_onload().pop(key, None)

    # applicability only matters until the e-Waybill is generated
    if doc.get("ewaybill"):
        if is_e_waybill_info_enabled() and (e_waybill_info := get_e_waybill_info(doc)):
            e_waybill_info.update(
                cancellable=is_e_waybill_cancellable(e_waybill_info),
                updatable=is_e_waybill_updatable(e_waybill_info),
                extendable=is_e_waybill_extendable(e_waybill_info),
                extendable_now=is_e_waybill_extendable_now(e_waybill_info),
            )
            doc.set_onload("e_waybill_info", e_waybill_info)

        return

    e_waybill_applicability = get_e_waybill_applicability(doc)

    # the client reads a missing key as all flags off
    if not e_waybill_applicability.is_enabled():
        return

    doc.set_onload("e_waybill_applicability", e_waybill_applicability.get())


@frappe.whitelist()
def get_e_waybill_applicability_reasons(doctype: str, docname: str):
    if doctype not in PERMITTED_DOCTYPES:
        frappe.throw(_("e-Waybill is not supported for {0}").format(_(doctype)))

    doc = frappe.get_lazy_doc(doctype, docname, check_permission="read")

    return get_e_waybill_applicability(doc).reasons


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
    # the portal allows cancelling for 24 hours after generation
    generated_on = e_waybill_info.get("created_on")
    return bool(generated_on) and add_days(generated_on, 1) >= get_datetime()


def is_e_waybill_updatable(e_waybill_info):
    # Part A alone has no validity yet
    valid_upto = e_waybill_info.get("valid_upto")
    return not valid_upto or get_datetime(valid_upto) >= get_datetime()


def is_e_waybill_extendable(e_waybill_info):
    # extendable until 8 hours after expiry; before that window it can be scheduled
    valid_upto = e_waybill_info.get("valid_upto")
    return bool(valid_upto) and get_datetime() - get_datetime(valid_upto) <= timedelta(hours=8)


def is_e_waybill_extendable_now(e_waybill_info):
    # the portal extends only within 8 hours either side of expiry
    valid_upto = e_waybill_info.get("valid_upto")
    return bool(valid_upto) and abs(get_datetime() - get_datetime(valid_upto)) <= timedelta(hours=8)


def get_e_waybill_info(doc):
    return frappe.db.get_value(
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
