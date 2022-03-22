import frappe
from frappe import _, bold

from india_compliance.gst_india.utils import validate_gstin


def update_transporter_gstin(doc, method=None):
    """
    Validate GST Transporter GSTIN with GSTIN if exists.
    """
    if not doc.is_transporter:
        return

    if doc.gstin:
        if doc.gstin != doc.gst_transporter_id:
            frappe.msgprint(
                _(
                    "GSTIN has been updated in GST Transporter ID from {0} to {1} as per default GSTIN for this transporter."
                ).format(bold(doc.gst_transporter_id), bold(doc.gstin)),
                alert=True,
                indicator="yellow",
            )
        doc.gst_transporter_id = doc.gstin

    elif doc.gst_transporter_id:
        validate_gstin(doc.gst_transporter_id, "Registered Regular")
