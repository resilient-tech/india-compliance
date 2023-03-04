import frappe

from india_compliance.gst_india.setup import (
    ITEM_VARIANT_FIELDNAMES,
    get_all_custom_fields,
    get_property_setters,
)
from india_compliance.gst_india.utils.custom_fields import delete_custom_fields


def before_uninstall():
    delete_custom_fields(get_all_custom_fields())
    delete_property_setters()
    remove_fields_from_item_variant_settings()


def delete_property_setters():
    field_map = {
        "doctype": "doc_type",
        "fieldname": "field_name",
    }

    for property_setter in get_property_setters():
        for key, fieldname in field_map.items():
            if key in property_setter:
                property_setter[fieldname] = property_setter.pop(key)

        frappe.db.delete("Property Setter", property_setter)


def remove_fields_from_item_variant_settings():
    settings = frappe.get_doc("Item Variant Settings")
    settings.fields = [
        row for row in settings.fields if row.field_name not in ITEM_VARIANT_FIELDNAMES
    ]
    settings.save()
