import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import cint

from india_compliance.audit_trail.setup import setup_versioning

TRACK_CHANGES_FILTERS = {
    "doctype_or_field": "DocType",
    "doc_type": "Sales Invoice",
    "property": "track_changes",
}


class TestAuditTrailSetup(IntegrationTestCase):
    def setUp(self):
        # set explicitly, since a previous run can leave this either way
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 0)

    def test_setup_versioning_forces_track_changes_and_clears_ignore_versioning(self):
        # set while the Audit Trail is off, so the validation does not kick in
        doc = frappe.get_doc(
            {
                "doctype": "Property Setter",
                "doctype_or_field": "DocField",
                "doc_type": "Sales Invoice",
                "field_name": "customer_name",
                "property": "ignore_versioning",
                "property_type": "Check",
                "value": 1,
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "Property Setter", doc.name, force=True)

        # drop it so the run has to create it again
        frappe.db.delete("Property Setter", TRACK_CHANGES_FILTERS)

        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 1)

        setup_versioning()

        # `track_changes` is forced on
        self.assertEqual(cint(frappe.db.get_value("Property Setter", TRACK_CHANGES_FILTERS, "value")), 1)

        # `Ignore Versioning` is cleared
        self.assertFalse(frappe.db.exists("Property Setter", doc.name))
