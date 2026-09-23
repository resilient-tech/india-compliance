import frappe

from india_compliance.gst_india.constants import TRANSPORTER_FIELDS
from india_compliance.gst_india.constants.custom_fields import E_WAYBILL_FIELDS


def execute():
    """Transport fields stay editable after e-Waybill, the form syncs changes to the portal."""
    doctypes = list(E_WAYBILL_FIELDS)

    # distance has no portal update
    unlock = set(TRANSPORTER_FIELDS) - {"distance"}

    frappe.db.set_value(
        "Custom Field",
        {"dt": ("in", doctypes), "fieldname": ("in", list(unlock))},
        "read_only_depends_on",
        None,
    )

    for doctype in doctypes:
        frappe.clear_cache(doctype=doctype)
