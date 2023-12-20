import frappe
from frappe import _


def get_company_gstin_number(company, address=None, all_gstins=False):
    gstin = ""
    if address:
        gstin = frappe.db.get_value("Address", address, "gstin")

    if not gstin:
        filters = [
            ["is_your_company_address", "=", 1],
            ["Dynamic Link", "link_doctype", "=", "Company"],
            ["Dynamic Link", "link_name", "=", company],
            ["Dynamic Link", "parenttype", "=", "Address"],
            ["gstin", "!=", ""],
        ]
        gstin = frappe.get_all(
            "Address",
            filters=filters,
            pluck="gstin",
            order_by="is_primary_address desc",
        )
        if gstin and not all_gstins:
            gstin = gstin[0]

    if not gstin:
        address = frappe.bold(address) if address else ""
        frappe.throw(
            _("Please set valid GSTIN No. in Company Address {} for company {}").format(
                address, frappe.bold(company)
            )
        )

    return gstin
