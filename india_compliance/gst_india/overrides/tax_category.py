import frappe
from frappe import _


def validate(doc, method=None):
    if not doc.get("is_india_compliance_default"):
        return

    existing = frappe.db.get_value(
        "Tax Category",
        {
            "name": ["!=", doc.name],
            "is_india_compliance_default": 1,
            "is_inter_state": doc.is_inter_state,
            "is_reverse_charge": doc.is_reverse_charge,
        },
    )
    if existing:
        frappe.throw(
            _(
                "An India Compliance Default Tax Category {0} already exists for this"
                " Inter State / Reverse Charge combination"
            ).format(frappe.bold(frappe.utils.get_link_to_form("Tax Category", existing)))
        )
