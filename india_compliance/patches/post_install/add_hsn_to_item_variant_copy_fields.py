import frappe

"""
This patch makes sure hsn code is copied over to variant item when created from template
"""


def execute():
    frappe.get_doc("Item Variant Settings").append(
        "fields", {"field_name": "gst_hsn_code"}
    ).save()
