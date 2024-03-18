import frappe


def execute():
    frappe.db.set_single_value(
        "GST Settings",
        {
            "inward_supply_period": 2,
            "reconcile_on_tuesday": 1,
            "reconcile_on_friday": 1,
            "reconcile_for_b2b": 1,
            "reconcile_for_cdnr": 1,
        },
    )
