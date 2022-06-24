import frappe


def execute():
    if not frappe.db.exists("Company", {"country": "India"}):
        return

    address = frappe.qb.DocType("Address")

    (
        frappe.qb.update(address)
        .set(address.gst_state, "Dadra and Nagar Haveli and Daman and Diu")
        .set(address.gst_state_number, "26")
        .where(address.gst_state == "Daman and Diu")
    ).run()
