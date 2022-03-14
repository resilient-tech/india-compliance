from email.policy import default

import frappe
from frappe import _

from india_compliance.gst_india.utils import validate_gstin


def update_transporter_gstin(doc, method=None):
    """
    Validate GST Transporter GSTIN with GSTIN if exists.
    """
    if not doc.is_transporter:
        return

    gstin = doc.get("gstin", default="")
    gst_transporter_id = doc.get("gst_transporter_id", default="")

    if not gstin and gst_transporter_id:
        validate_gstin(gst_transporter_id, "Registered Regular")

    if gst_transporter_id and gst_transporter_id != gstin:
        frappe.msgprint(
            _(
                "GSTIN has been updated in GST Transporter ID from {0} to {1} as per default GSTIN for this transporter."
            ).format(frappe.bold(gst_transporter_id), frappe.bold(gstin))
        )
    doc.gst_transporter_id = gstin
