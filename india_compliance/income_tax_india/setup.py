import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from india_compliance.income_tax_india.constants.custom_fields import CUSTOM_FIELDS


def after_install():
    create_custom_fields(CUSTOM_FIELDS, update=True)
    create_gratuity_rule_for_india()


def create_gratuity_rule_for_india():
    if not frappe.db.exists("DocType", "Gratuity Rule"):
        return

    _create_gratuity_rule_for_india()


def _create_gratuity_rule_for_india():
    if frappe.db.exists("Gratuity Rule", "Indian Standard Gratuity Rule"):
        return

    rule = frappe.new_doc("Gratuity Rule")
    rule.update(
        {
            "name": "Indian Standard Gratuity Rule",
            "calculate_gratuity_amount_based_on": "Current Slab",
            "work_experience_calculation_method": "Round Off Work Experience",
            "minimum_year_for_gratuity": 5,
            "gratuity_rule_slabs": [
                {
                    "from_year": 0,
                    "to_year": 0,
                    "fraction_of_applicable_earnings": 15 / 26,
                }
            ],
        }
    )
    rule.flags.ignore_mandatory = True
    rule.save()
