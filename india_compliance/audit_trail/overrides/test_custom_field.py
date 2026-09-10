import re

import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.audit_trail.overrides.custom_field import validate
from india_compliance.audit_trail.utils import get_audit_trail_doctypes


class TestCustomField(IntegrationTestCase):
    def setUp(self):
        # set explicitly, since a previous run can leave this either way
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 1)
        self.addCleanup(frappe.db.set_single_value, "Accounts Settings", "enable_audit_trail", 0)

    def get_ignore_versioning_custom_field(self, doctype):
        return frappe.get_doc(
            {
                "doctype": "Custom Field",
                "dt": doctype,
                "fieldname": "_test_ignore_versioning",
                "label": "Test Ignore Versioning",
                "fieldtype": "Data",
                "ignore_versioning": 1,
            }
        )

    def insert_ignore_versioning_custom_field(self, doctype):
        # a previous run can leave the field behind: inserting one runs DDL, which commits
        # in MariaDB, while the cleanup delete is rolled back with the test transaction
        frappe.db.delete("Custom Field", {"dt": doctype, "fieldname": "_test_ignore_versioning"})
        frappe.clear_cache(doctype=doctype)

        doc = self.get_ignore_versioning_custom_field(doctype)
        doc.insert(ignore_permissions=True)
        self.addCleanup(doc.delete)

        return doc

    def assertCannotEnableIgnoreVersioning(self, fn):
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Cannot enable Ignore Versioning for*)"),
            fn,
        )

    def test_ignore_versioning_cannot_be_enabled_for_audit_trail_doctype(self):
        doc = self.get_ignore_versioning_custom_field("Sales Invoice")

        self.assertCannotEnableIgnoreVersioning(doc.insert)

    def test_ignore_versioning_cannot_be_enabled_for_child_table(self):
        # child table changes are recorded in the parent's Version
        self.assertIn("Sales Invoice Item", get_audit_trail_doctypes(include_child=True))

        doc = self.get_ignore_versioning_custom_field("Sales Invoice Item")

        self.assertCannotEnableIgnoreVersioning(doc.insert)

    def test_ignore_versioning_is_allowed_for_other_doctypes(self):
        doc = self.get_ignore_versioning_custom_field("ToDo")

        # validated without saving, since inserting a Custom Field commits in MariaDB
        validate(doc)

        self.assertEqual(doc.ignore_versioning, 1)

    def test_existing_ignore_versioning_is_kept(self):
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 0)

        # the user's own choice, made before the Audit Trail was enabled
        doc = self.insert_ignore_versioning_custom_field("Sales Invoice")
        self.assertEqual(doc.ignore_versioning, 1)

        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 1)

        # the value is unchanged, so it is left as it is
        doc.label = "Test Ignore Versioning Renamed"
        doc.save()

        self.assertEqual(doc.ignore_versioning, 1)
