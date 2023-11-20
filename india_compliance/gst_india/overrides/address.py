import frappe
from frappe import _

from india_compliance.gst_india.constants import STATE_NUMBERS
from india_compliance.gst_india.overrides.party import set_gst_category
from india_compliance.gst_india.utils import (
    validate_gst_category,
    validate_gstin,
    validate_pincode,
)


def validate(doc, method=None):
    doc.gstin = validate_gstin(doc.gstin)
    set_gst_category(doc)
    validate_gst_category(doc.gst_category, doc.gstin)
    validate_overseas_gst_category(doc)
    validate_state(doc)
    validate_pincode(doc)


def validate_overseas_gst_category(doc):
    if doc.country == "India" and doc.gst_category == "Overseas":
        frappe.throw(
            _("Cannot set GST Category as Overseas for Indian Address"),
            title=_("Invalid GST Category"),
        )

    if doc.country != "India" and doc.gst_category != "Overseas":
        frappe.throw(
            _("GST Category should be set to Overseas for Address outside India"),
            title=_("Invalid GST Category"),
        )


def validate_state(doc):
    """
    - Validate State to be a mandatory field.
    - Set GST State and State Number.
    - Update State with GST State.
    - Validate GST State Number with GSTIN.
    """
    if doc.country != "India":
        doc.gst_state = None
        doc.gst_state_number = None
        return

    if not doc.state:
        frappe.throw(
            _("State is a required field for Indian Address"),
            title=_("Missing Mandatory Field"),
        )

    if doc.state not in STATE_NUMBERS:
        frappe.throw(
            _("Please select a valid State from available options"),
            title=_("Invalid State"),
        )

    # TODO: deprecate these fields
    doc.gst_state = doc.state
    doc.gst_state_number = STATE_NUMBERS[doc.state]

    if doc.gstin and doc.gst_state_number != doc.gstin[:2]:
        frappe.throw(
            _(
                "First 2 digits of GSTIN should match with State Number for {0} ({1})"
            ).format(frappe.bold(doc.gst_state), doc.gst_state_number),
            title=_("Invalid GSTIN or State"),
        )
