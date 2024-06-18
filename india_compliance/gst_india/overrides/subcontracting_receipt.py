import frappe

from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.e_waybill import get_e_waybill_info
from india_compliance.gst_india.utils.taxes_controller import (
    before_save as _before_save,
)
from india_compliance.gst_india.utils.taxes_controller import (
    before_submit as _before_submit,
)
from india_compliance.gst_india.utils.taxes_controller import (
    before_validate as _before_validate,
)
from india_compliance.gst_india.utils.taxes_controller import validate as _validate


def onload(doc, method=None):
    if not doc.get("ewaybill"):
        return

    gst_settings = frappe.get_cached_doc("GST Settings")

    if not (
        is_api_enabled(gst_settings)
        and gst_settings.enable_e_waybill
        and gst_settings.enable_e_waybill_for_sc
    ):
        return

    doc.set_onload("e_waybill_info", get_e_waybill_info(doc))


def before_save(doc, method=None):
    _before_save(doc)


def before_submit(doc, method=None):
    _before_submit(doc)


def before_validate(doc, method=None):
    _before_validate(doc)


def validate(doc, method=None):
    _validate(doc)
