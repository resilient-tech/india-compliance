import frappe
from frappe import _

from india_compliance.gst_india.utils import (
    set_gst_state_and_state_number,
    validate_gstin,
)


def validate(doc, method=None):
    doc.gstin = (doc.get("gstin") or "").upper().strip()
    validate_gstin(doc.gstin, doc.gst_category)
    validate_gst_state(doc)


def validate_gst_state(doc):
    """
    Added Validation for State to be a mandatory field for Address.
    Set GST State and State Number and validate it with GSTIN.
    """
    if doc.get("gst_category") == "Overseas" or doc.country != "India":
        return

    if not doc.get("state"):
        frappe.throw(
            _("State is Mandatory in Address for India."),
            title=_("Missing Mandatory Field"),
        )

    set_gst_state_and_state_number(doc)

    if doc.get("gstin") and doc.gst_state_number != doc.gstin[:2]:
        frappe.throw(
            _("First 2 digits of GSTIN should match with State number {0}.").format(
                doc.gst_state_number
            ),
            title=_("Invalid GSTIN or State"),
        )
