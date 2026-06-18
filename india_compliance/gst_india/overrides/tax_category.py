import frappe
from frappe import _


def validate(doc, method=None):
    if doc.get("is_india_compliance_default") and doc.get("gst_state"):
        frappe.throw(_("India Compliance Default Tax Category cannot have a Source State"))

    if doc.get("is_india_compliance_default"):
        if frappe.db.exists(
            "Tax Category",
            {
                "name": ["!=", doc.name],
                "is_india_compliance_default": 1,
                "is_inter_state": doc.is_inter_state,
                "is_reverse_charge": doc.is_reverse_charge,
            },
        ):
            frappe.throw(
                _(
                    "An India Compliance Default Tax Category already exists for this"
                    " Inter State / Reverse Charge combination"
                )
            )

    elif doc.get("gst_state") and frappe.db.exists(
        "Tax Category",
        {
            "name": ["!=", doc.name],
            "gst_state": doc.gst_state,
            "is_inter_state": doc.is_inter_state,
            "is_reverse_charge": doc.is_reverse_charge,
        },
    ):
        if doc.is_inter_state:
            frappe.throw(_("Inter State tax category for GST State {0} already exists").format(doc.gst_state))
        else:
            frappe.throw(_("Intra State tax category for GST State {0} already exists").format(doc.gst_state))
