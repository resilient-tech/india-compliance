import frappe
from frappe import _

from india_compliance.gst_india.utils import get_gst_state_details, validate_gstin


def validate(doc, method=None):
    doc.gstin = doc.gstin.upper().strip()
    validate_gstin(doc.gstin, doc.gst_category)
    validate_gst_state(doc)


def validate_gst_state(doc):
    """
    - Validate State to be a mandatory field.
    - Set GST State and State Number.
    - Update State with GST State.
    - Validate GST State Number with GSTIN.
    """
    if doc.gst_category == "Overseas" or doc.country != "India":
        return

    if not doc.state:
        frappe.throw(
            _("State is Mandatory in Address for India."),
            title=_("Missing Mandatory Field"),
        )

    state, state_number = get_gst_state_details(doc.state)
    doc.state = doc.gst_state = state
    doc.gst_state_number = state_number

    if doc.gstin and doc.gst_state_number != doc.gstin[:2]:
        frappe.throw(
            _("First 2 digits of GSTIN should match with State number {0}.").format(
                doc.gst_state_number
            ),
            title=_("Invalid GSTIN or State"),
        )
