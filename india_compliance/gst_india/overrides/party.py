import frappe
from frappe import _


def update_gstin_in_address(doc, method):
    if doc.has_value_changed("gstin"):
        addresses = frappe.get_all(
            "Address",
            filters=[
                ["Address", "use_different_gstin", "=", 0],
                ["Dynamic Link", "link_doctype", "=", doc.doctype],
                ["Dynamic Link", "link_name", "=", doc.name],
                ["Dynamic Link", "parenttype", "=", "Address"],
            ],
            fields=["name"],
        )

        frappe.db.set_value(
            "Address",
            {"name": ["in", [address["name"] for address in addresses]]},
            "gstin",
            doc.gstin,
        )

        frappe.msgprint(_("GSTIN has been updated to the linked addresses."))
