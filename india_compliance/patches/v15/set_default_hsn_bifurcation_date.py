import frappe


def execute():
    frappe.db.set_single_value("GST Settings", "hsn_bifurcation_from", "2025-04-01")
