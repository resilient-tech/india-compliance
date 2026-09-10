import re

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import cint

from india_compliance.audit_trail.setup import delete_ignore_versioning_property_setters
from india_compliance.audit_trail.utils import get_audit_trail_doctypes


class TestPropertySetter(IntegrationTestCase):
    def setUp(self):
        # set explicitly, since a previous run can leave this either way
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 0)

    def enable_audit_trail(self):
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 1)
        self.addCleanup(frappe.db.set_single_value, "Accounts Settings", "enable_audit_trail", 0)

    def test_validate_property_setter_where_audit_trail_enabled_and_doc_is_protected(
        self,
    ):
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 1)
        frappe.db.delete(
            "Property Setter",
            {
                "doctype_or_field": "DocType",
                "doc_type": "Purchase Invoice",
                "property": "track_changes",
            },
        )

        doc = frappe.get_doc(
            {
                "doctype": "Property Setter",
                "doctype_or_field": "DocType",
                "doc_type": "Purchase Invoice",
                "property": "track_changes",
                "value": 1,
            },
        )
        doc.save()
        doc.value = 0

        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Cannot change the Track Changes property for*)"),
            doc.save,
        )

        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Cannot change the Track Changes property for*)"),
            doc.delete,
        )
        doc.reload()
        doc.doc_type = "Address"
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Cannot change the Track Changes property for*)"),
            doc.save,
        )
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 0)
        doc.delete()

    def get_ignore_versioning_property_setter(self, doctype, fieldname):
        return frappe.get_doc(
            {
                "doctype": "Property Setter",
                "doctype_or_field": "DocField",
                "doc_type": doctype,
                "field_name": fieldname,
                "property": "ignore_versioning",
                "property_type": "Check",
                "value": 1,
            }
        )

    def insert_ignore_versioning_property_setter(self, doctype, fieldname):
        doc = self.get_ignore_versioning_property_setter(doctype, fieldname)
        doc.insert(ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "Property Setter", doc.name, force=True)

        return doc

    def assertCannotEnableIgnoreVersioning(self, fn):
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Cannot enable Ignore Versioning for*)"),
            fn,
        )

    def test_ignore_versioning_cannot_be_enabled_for_audit_trail_doctypes(self):
        self.enable_audit_trail()

        doc = self.get_ignore_versioning_property_setter("Sales Invoice", "customer_name")
        self.assertCannotEnableIgnoreVersioning(doc.insert)

        # child table changes are recorded in the parent's Version
        self.assertIn("Sales Invoice Item", get_audit_trail_doctypes(include_child=True))

        child_doc = self.get_ignore_versioning_property_setter("Sales Invoice Item", "item_name")
        self.assertCannotEnableIgnoreVersioning(child_doc.insert)

    def test_ignore_versioning_is_allowed_for_other_doctypes(self):
        self.enable_audit_trail()

        doc = self.insert_ignore_versioning_property_setter("ToDo", "description")

        self.assertEqual(cint(doc.value), 1)

    def test_ignore_versioning_is_enforced_even_if_value_is_unchanged(self):
        # set before Audit Trail is enabled, so the validation does not kick in
        doc = self.insert_ignore_versioning_property_setter("Sales Invoice", "customer_name")
        self.assertEqual(cint(doc.value), 1)

        self.enable_audit_trail()

        # a Property Setter sits on a standard field, so any save is refused
        self.assertCannotEnableIgnoreVersioning(doc.save)

    def test_cleanup_deletes_ignore_versioning_property_setters(self):
        # set before Audit Trail is enabled, so the validation does not kick in
        doc = self.insert_ignore_versioning_property_setter("Sales Invoice", "customer_name")

        self.enable_audit_trail()

        delete_ignore_versioning_property_setters()

        self.assertFalse(frappe.db.exists("Property Setter", doc.name))
