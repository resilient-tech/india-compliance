import frappe
from frappe import _


def validate(doc, method=None):
    if doc.get("gst_state") and frappe.db.get_value(
        "Tax Category",
        {
            "gst_state": doc.gst_state,
            "is_inter_state": doc.is_inter_state,
            "is_reverse_charge": doc.is_reverse_charge,
        },
    ):
        if doc.is_inter_state:
            frappe.throw(
                _("Inter State tax category for GST State {0} already exists").format(
                    doc.gst_state
                )
            )
        else:
            frappe.throw(
                _("Intra State tax category for GST State {0} already exists").format(
                    doc.gst_state
                )
            )
