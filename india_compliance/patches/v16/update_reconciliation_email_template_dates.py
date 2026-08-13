import re

import frappe

# purchase and inward supply filters became one: period, from_date, to_date
OLD_FIELDS = re.compile(r"\b(?:purchase|inward_supply)_(period|from_date|to_date)\b")
TEMPLATE_FIELDS = ("subject", "response", "response_html")


def execute():
    or_filters = {"name": "Purchase Reconciliation"}
    if frappe.db.has_column("Email Template", "reference_doctype"):
        or_filters["reference_doctype"] = "Purchase Reconciliation Tool"

    templates = frappe.get_all(
        "Email Template",
        or_filters=or_filters,
        fields=("name", *TEMPLATE_FIELDS),
    )

    for template in templates:
        updates = {
            field: OLD_FIELDS.sub(r"\1", value)
            for field in TEMPLATE_FIELDS
            if (value := template[field]) and OLD_FIELDS.search(value)
        }

        if updates:
            frappe.db.set_value("Email Template", template.name, updates)
