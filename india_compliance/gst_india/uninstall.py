import frappe

from india_compliance.gst_india.setup import (
    HRMS_CUSTOM_FIELDS,
    ITEM_VARIANT_FIELDNAMES,
    get_all_custom_fields,
    get_property_setters,
)
from india_compliance.gst_india.utils.custom_fields import delete_custom_fields


def before_uninstall():
    delete_custom_fields(get_all_custom_fields())
    delete_hrms_custom_fields()
    delete_property_setters()
    delete_accounting_dimension_fields()
    remove_fields_from_item_variant_settings()


def delete_hrms_custom_fields():
    delete_custom_fields(HRMS_CUSTOM_FIELDS)


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


def delete_accounting_dimension_fields():
    doctypes = frappe.get_hooks(
        "accounting_dimension_doctypes",
        app_name="india_compliance",
    )

    fieldnames = frappe.get_all("Accounting Dimension", fields=["fieldname"])
    delete_custom_fields({doctype: fieldnames for doctype in doctypes})


def remove_fields_from_item_variant_settings():
    settings = frappe.get_doc("Item Variant Settings")
    settings.fields = [
        row for row in settings.fields if row.field_name not in ITEM_VARIANT_FIELDNAMES
    ]
    settings.save()
