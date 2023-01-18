import frappe

"""
This patch makes sure hsn code is copied over to variant item when created from template
"""


def execute():
    ivs = frappe.get_doc("Item Variant Settings")
    fields_to_add = ["gst_hsn_code", "is_nil_exempt", "is_non_gst"]
    existing_fields = frappe.db.get_all(
        "Variant Field", {"field_name": ["in", fields_to_add]}, pluck="field_name"
    )
    if len(existing_fields) == 3:
        return
    [
        ivs.append("fields", {"field_name": d})
        for d in fields_to_add
        if d not in existing_fields
    ]
    ivs.save()
