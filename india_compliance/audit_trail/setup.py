import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from india_compliance.audit_trail.constants.custom_fields import CUSTOM_FIELDS
from india_compliance.audit_trail.utils import (
    get_audit_trail_doctypes,
    is_audit_trail_enabled,
)


def setup_fixtures():
    create_custom_fields(CUSTOM_FIELDS)
    create_property_setters_for_versioning()


def create_property_setters_for_versioning():
    for doctype in get_audit_trail_doctypes():
        property_setter = frappe.new_doc("Property Setter")
        property_setter.update(
            {
                "doctype_or_field": "DocType",
                "doc_type": doctype,
                "property": "track_changes",
                "value": "1",
                "property_type": "Check",
                "is_system_generated": 1,
            }
        )
        property_setter.flags.ignore_permissions = True
        property_setter.flags.for_audit_trail = True
        property_setter.insert()


def after_migrate():
    if is_audit_trail_enabled():
        create_property_setters_for_versioning()
