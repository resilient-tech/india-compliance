import frappe


def execute():
    reverse_charge_tax_category = frappe.db.get_all(
        "Tax Category",
        filters={"is_reverse_charge": "1"},
        pluck="name",
    )

    if not reverse_charge_tax_category:
        return

    frappe.db.set_value(
        "Supplier",
        {"tax_category": ("in", reverse_charge_tax_category)},
        "is_reverse_charge_applicable",
        1,
    )
