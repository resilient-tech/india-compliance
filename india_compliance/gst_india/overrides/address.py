import frappe
from frappe import _

from india_compliance.gst_india.utils import (
    set_gst_state_and_state_number,
    validate_gstin,
)


def validate(doc, method=None):
    update_default_gst_details(doc)

    doc.gstin = doc.gstin.upper().strip() if doc.get("gstin") else ""
    validate_gstin(doc.gstin, doc.gst_category)
    validate_gst_state(doc)


def update_default_gst_details(doc):
    if not doc.use_different_gstin:
        if doc.links:
            doc.gstin, doc.gst_category = frappe.db.get_value(
                doc.links[0].link_doctype,
                doc.links[0].link_name,
                ["gstin", "gst_category"],
            )

    if doc.gstin and not doc.links:
        doc.gstin = ""
        doc.gst_category = ""

    doc.use_different_gstin = True if len(doc.links) > 1 else False


def validate_gst_state(doc):
    if doc.get("gst_category") == "Overseas" or doc.country != "India":
        return

    set_gst_state_and_state_number(doc)

    if doc.get("gstin") and doc.gst_state_number != doc.gstin[:2]:
        frappe.throw(
            _("First 2 digits of GSTIN should match with State number {0}.").format(
                doc.gst_state_number
            ),
            title=_("Invalid GSTIN"),
        )
