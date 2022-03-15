import frappe
from frappe import _

from india_compliance.gst_india.utils import validate_and_update_pan, validate_gstin


def validate_party(doc, method=None):
    doc.gstin = (doc.get("gstin") or "").upper().strip()
    validate_gstin(doc.gstin, doc.gst_category)
    validate_and_update_pan(doc)
    update_gstin_in_address(doc)


def update_gstin_in_address(doc):
    """
    Identify addresses which uses party's GSTIN and update
    their GSTIN and GST Category.
    """
    if not doc.has_value_changed("gstin"):
        return

    addresses = frappe.get_all(
        "Address",
        filters=[
            ["Address", "use_party_gstin", "=", 1],
            ["Dynamic Link", "link_doctype", "=", doc.doctype],
            ["Dynamic Link", "link_name", "=", doc.name],
            ["Dynamic Link", "parenttype", "=", "Address"],
        ],
        fields=["name"],
    )

    frappe.db.set_value(
        "Address",
        {"name": ["in", [address["name"] for address in addresses]]},
        {"gstin": doc.gstin, "gst_category": doc.gst_category},
    )

    frappe.msgprint(
        _(
            "GSTIN and its Category has been updated to all linked addresses where you are using same GSTIN."
        )
    )
