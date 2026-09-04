# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe


def get_msme_details(party_details) -> dict:
    """
    Get MSME registration linked to supplier
    """
    supplier = party_details.get("supplier")
    if not supplier:
        return {}

    return {"msme_registration": frappe.db.get_value("Supplier", supplier, "msme_registration")}
