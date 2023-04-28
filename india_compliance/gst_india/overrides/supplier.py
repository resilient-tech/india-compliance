import frappe
from frappe import _, bold

from india_compliance.gst_india.constants import REGISTERED
from india_compliance.gst_india.utils import validate_gstin


def validate_gst_transporter_id(doc, method=None):
    """
    - Set as GSTIN if not set
    - Match PAN with GSTIN
    - Validate length, check digit and format (as applicable)
    """
    if not doc.is_transporter:
        return

    if doc.gstin:
        if not doc.gst_transporter_id:
            doc.gst_transporter_id = doc.gstin
            frappe.msgprint(
                _(
                    "GST Transporter ID has been updated to {0} as per the default"
                    " GSTIN for this transporter."
                ).format(bold(doc.gstin)),
                alert=True,
            )
            return

        pan_from_transporter_id = doc.gst_transporter_id[2:12]
        pan_from_gstin = doc.gstin[2:12]

        if pan_from_transporter_id != pan_from_gstin:
            frappe.throw(
                _(
                    "The PAN extracted from GST Transporter ID ({0}) doesn't match"
                    " the PAN extracted from GSTIN ({1}). Please correct"
                    " the GST Transporter ID or GSTIN."
                ).format(bold(pan_from_transporter_id), bold(pan_from_gstin)),
                title=_("PAN Mismatch in GST Transporter ID and GSTIN"),
            )

    if not doc.gst_transporter_id:
        return

    doc.gst_transporter_id = validate_gstin(
        doc.gst_transporter_id,
        _("GST Transporter ID"),
        is_transporter_id=True,
    )

    if not REGISTERED.match(doc.gst_transporter_id):
        frappe.throw(
            _(
                "The GST Transporter ID you've entered doesn't match the required"
                " format"
            ),
            title=_("Invalid GST Transporter ID"),
        )
