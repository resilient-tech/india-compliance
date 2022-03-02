import frappe

from india_compliance.income_tax_india.setup import \
    _create_gratuity_rule_for_india


def create_gratuity_rule_for_india(doc, method=None):
    if doc.name != "Gratuity Rule" or frappe.db.exists(
        "Gratuity Rule", "Indian Standard Gratuity Rule"
    ):
        return

    _create_gratuity_rule_for_india()
