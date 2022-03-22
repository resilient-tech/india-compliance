import frappe
from frappe import _

from india_compliance.gst_india.utils import validate_gstin


def update_transporter_gstin(doc, method=None):
    """
    Validate GST Transporter GSTIN with GSTIN if exists.
    """
    if not doc.is_transporter:
        return

    if doc.gstin and doc.gstin != doc.gst_transporter_id:
        doc.gst_transporter_id = doc.gstin
        frappe.msgprint(
            _(
                "GSTIN has been updated in GST Transporter ID from {0} to {1} as per default GSTIN for this transporter."
            ).format(frappe.bold(doc.gst_transporter_id), frappe.bold(doc.gstin))
        )

    elif doc.gst_transporter_id:
        validate_gstin(doc.gst_transporter_id, "Registered Regular")
