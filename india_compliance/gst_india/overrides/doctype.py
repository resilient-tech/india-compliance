import frappe


def create_gratuity_rule_for_india(doc, method=None):
    if (
        doc.name != "Gratuity Rule"
        or frappe.db.exists("Gratuity Rule", "Indian Standard Gratuity Rule")
    ):
        return

    rule = frappe.get_doc(
        {
            "doctype": "Gratuity Rule",
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
