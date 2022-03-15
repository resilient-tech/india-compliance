import frappe
from frappe import _

from india_compliance.gst_india.utils import (
    set_gst_state_and_state_number,
    validate_gstin,
)


def validate(doc, method=None):
    update_default_gst_details(doc)

    doc.gstin = (doc.get("gstin") or "").upper().strip()
    validate_gstin(doc.gstin, doc.gst_category)
    validate_gst_state(doc)


def update_default_gst_details(doc):
    """
    In following cases update GST Details:
    - For New Address. If more than one party, pick first GSTIN and update `use_party_gstin` as false.
    - If linked party has changed, update GST Details.
    - If no linked party, update GSTIN and GST Category to null if exists.
    """

    if not doc.use_party_gstin:
        return

    if doc.links:
        doc.gstin, doc.gst_category = frappe.db.get_value(
            doc.links[0].link_doctype,
            doc.links[0].link_name,
            ["gstin", "gst_category"],
        )

    if has_more_links := len(doc.links) > 1:
        frappe.msgprint(
            _("`Use Party GSTIN` is not supported for address with multiple parties."),
            alert=True,
            indicator="yellow",
        )

    doc.use_party_gstin = False if has_more_links else True

    if doc.gstin and not doc.links:
        doc.gstin = ""
        doc.gst_category = ""


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
