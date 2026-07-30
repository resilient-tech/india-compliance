import frappe

# purchase and inward supply date filters became one, {{ from_date }} / {{ to_date }}
OLD_DATES = "{{ inward_supply_from_date }} to {{ inward_supply_to_date }}"
NEW_DATES = "{{ from_date }} to {{ to_date }}"


def execute():
    response = frappe.db.get_value("Email Template", "Purchase Reconciliation", "response")
    if not response or OLD_DATES not in response:
        return

    frappe.db.set_value(
        "Email Template",
        "Purchase Reconciliation",
        "response",
        response.replace(OLD_DATES, NEW_DATES),
    )
