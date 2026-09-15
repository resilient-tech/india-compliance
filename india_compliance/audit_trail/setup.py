import frappe

from india_compliance.audit_trail.constants.custom_fields import CUSTOM_FIELDS
from india_compliance.audit_trail.utils import (
    get_audit_trail_doctypes,
    is_audit_trail_enabled,
)
from india_compliance.utils.custom_fields import get_custom_fields_creator

_create_custom_fields = get_custom_fields_creator("Audit Trail")


# Hooks


def setup_fixtures():
    """
    Runs when the app is installed.
    """
    create_custom_fields()
    create_property_setters_for_versioning()


def create_custom_fields():
    _create_custom_fields(CUSTOM_FIELDS)


def create_property_setters_for_versioning():
    for doctype in get_audit_trail_doctypes():
        property_setter_data = {
            "doctype_or_field": "DocType",
            "doc_type": doctype,
            "property": "track_changes",
            "value": "1",
            "property_type": "Check",
            "is_system_generated": 1,
        }

        if frappe.db.exists("Property Setter", property_setter_data):
            continue

        property_setter = frappe.new_doc("Property Setter")
        property_setter.update(property_setter_data)
        property_setter.flags.ignore_permissions = True
        property_setter.insert()


def setup_versioning():
    """
    Runs on migrate and when the Audit Trail gets enabled.

    Custom Fields are skipped, since those are the user's own fields.
    """
    create_property_setters_for_versioning()
    delete_ignore_versioning_property_setters()


def delete_ignore_versioning_property_setters():
    filters = {
        "doctype_or_field": "DocField",
        "property": "ignore_versioning",
        "value": "1",
        "doc_type": ("in", get_audit_trail_doctypes(include_children=True)),
    }

    property_setters = frappe.get_all("Property Setter", filters=filters, fields=["name", "doc_type"])
    if not property_setters:
        return

    frappe.db.delete("Property Setter", {"name": ("in", {ps.name for ps in property_setters})})

    for doctype in {ps.doc_type for ps in property_setters}:
        frappe.clear_cache(doctype=doctype)


def after_migrate():
    if is_audit_trail_enabled():
        setup_versioning()
