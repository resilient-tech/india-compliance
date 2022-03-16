import frappe


def execute():
    tax_category = frappe.qb.DocType("Tax Category")

    frappe.qb.update(tax_category).set(tax_category.is_reverse_charge, 1).where(
        tax_category.name.isin(("Reverse Charge Out-State", "Reverse Charge In-State"))
    ).run()
