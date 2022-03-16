import frappe


def execute():
    # Create tax category with inter state field checked
    tax_category = frappe.db.get_value("Tax Category", {"name": "OUT OF STATE"})

    if not tax_category:
        inter_state_category = frappe.get_doc(
            {"doctype": "Tax Category", "title": "OUT OF STATE", "is_inter_state": 1}
        ).insert()

        tax_category = inter_state_category.name

    for part in ("Sales", "Purchase"):
        doctype = f"{part} Taxes and Charges Template"
        if not frappe.get_meta(doctype).has_field("is_inter_state"):
            continue

        template = frappe.db.get_value(doctype, {"is_inter_state": 1, "disabled": 0})
        if template:
            frappe.db.set_value(doctype, template, "tax_category", tax_category)

    frappe.db.sql(
        """
        DELETE FROM `tabCustom Field`
        WHERE fieldname = 'is_inter_state'
        AND dt IN ('Sales Taxes and Charges Template', 'Purchase Taxes and Charges Template')
    """
    )
