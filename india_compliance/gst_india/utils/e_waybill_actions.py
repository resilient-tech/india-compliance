"""What a document can do with its e-Waybill: generate it, auto-generate it, cancel it."""

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime

from india_compliance.gst_india.constants.e_waybill import PERMITTED_DOCTYPES
from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.e_waybill_applicability import get_e_waybill_applicability


def is_e_waybill_enabled(doc):
    return get_e_waybill_applicability(doc).is_enabled()


def is_e_waybill_api_enabled(doc):
    return get_e_waybill_applicability(doc).is_api_enabled()


def is_e_waybill_applicable(doc):
    return get_e_waybill_applicability(doc).is_applicable()


def is_e_waybill_generatable(doc):
    return get_e_waybill_applicability(doc).is_generatable()


def is_e_waybill_required(doc):
    return get_e_waybill_applicability(doc).is_required()


def is_e_waybill_auto_generatable(doc):
    return get_e_waybill_applicability(doc).is_auto_generatable()


def set_e_waybill_applicability(doc, method=None):
    e_waybill_applicability = get_e_waybill_applicability(doc)

    # the client reads a missing key as all flags off
    if doc.get("ewaybill") or not e_waybill_applicability.is_enabled():
        return

    applicability = e_waybill_applicability.get()
    applicability.pop("reasons")

    doc.set_onload("e_waybill_applicability", applicability)


@frappe.whitelist()
def get_e_waybill_applicability_reasons(doctype: str, docname: str):
    if doctype not in PERMITTED_DOCTYPES:
        frappe.throw(_("e-Waybill is not supported for {0}").format(_(doctype)))

    doc = frappe.get_lazy_doc(doctype, docname, check_permission="read")

    return get_e_waybill_applicability(doc).get().reasons


def is_e_waybill_info_enabled(gst_settings=None):
    gst_settings = gst_settings or frappe.get_cached_doc("GST Settings")

    # the doctype switch governs new e-Waybills; an existing one stays manageable
    return bool(gst_settings.enable_e_waybill and is_api_enabled(gst_settings))


def is_e_waybill_cancellable(doc, e_waybill_info=None):
    if not (doc.get("ewaybill") and is_e_waybill_info_enabled()):
        return False

    e_waybill_info = e_waybill_info or doc.get_onload().get("e_waybill_info") or {}
    generated_on = e_waybill_info.get("created_on")

    # the portal allows cancelling for 24 hours after generation
    return bool(generated_on) and add_days(generated_on, 1) >= get_datetime()


def is_e_waybill_auto_cancellable(doc, e_waybill_info=None):
    return bool(frappe.get_cached_doc("GST Settings").auto_cancel_e_waybill) and is_e_waybill_cancellable(
        doc, e_waybill_info
    )
