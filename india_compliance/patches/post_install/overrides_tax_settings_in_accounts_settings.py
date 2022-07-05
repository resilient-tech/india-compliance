import frappe


def execute():
    if frappe.db.get_value("Global Defaults", None, "country") != "India":
        return

    frappe.db.set_value(
        "Accounts Settings",
        None,
        {
            "determine_address_tax_category_from": "Billing Address",
            "add_taxes_from_item_tax_template": 0,
        },
    )
