import frappe
from frappe.utils import cstr


def update_place_of_supply(doc, method):
    country = frappe.get_cached_value("Company", doc.company, "country")
    if country != "India":
        return

    address = frappe.db.get_value(
        "Address",
        doc.get("customer_address"),
        ["gst_state", "gst_state_number"],
        as_dict=1,
    )
    if address and address.gst_state and address.gst_state_number:
        doc.place_of_supply = (
            cstr(address.gst_state_number) + "-" + cstr(address.gst_state)
        )
