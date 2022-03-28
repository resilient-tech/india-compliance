import frappe
from frappe import _, bold

from india_compliance.gst_india.constants import REGISTERED
from india_compliance.gst_india.utils import validate_gstin


def update_transporter_gstin(doc, method=None):
    """
    Validate GST Transporter GSTIN with GSTIN if exists.
    """
    if not doc.is_transporter:
        return

    if doc.gstin:
        if doc.gstin != doc.gst_transporter_id:
            doc.gst_transporter_id = doc.gstin
            frappe.msgprint(
                _(
                    "GST Transporter ID has been updated to {0} as per the default"
                    " GSTIN for this transporter."
                ).format(bold(doc.gstin)),
                alert=True,
            )

        return

    if not doc.gst_transporter_id:
        return

    doc.gst_transporter_id = validate_gstin(
        doc.gst_transporter_id, _("GST Transporter ID")
    )

    if not REGISTERED.match(doc.gst_transporter_id):
        frappe.throw(
            _(
                "The GST Transporter ID you've entered doesn't match the required"
                " format"
            ),
            title=_("Invalid GST Transporter ID"),
        )
