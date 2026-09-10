import re

import frappe
from frappe.tests import IntegrationTestCase


class TestCustomizeFormAuditTrail(IntegrationTestCase):
    def test_validate_customize_form(self):
        customize_frm = self.get_customize_form()
        customize_frm.doc_type = "Purchase Invoice"
        customize_frm.save_customization()

        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 1)

        customize_frm.track_changes = 0
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Cannot disable Track Changes for*)"),
            customize_frm.save_customization,
        )
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 0)

    def test_audit_trail_enabled_onload_covers_child_tables(self):
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 1)
        self.addCleanup(frappe.db.set_single_value, "Accounts Settings", "enable_audit_trail", 0)

        # versioning enforcement covers child tables, unlike `track_changes`
        self.assertTrue(self.get_customize_form("Sales Invoice").get_onload("audit_trail_enabled"))
        self.assertTrue(self.get_customize_form("Sales Invoice Item").get_onload("audit_trail_enabled"))
        self.assertFalse(self.get_customize_form("ToDo").get_onload("audit_trail_enabled"))

    def get_customize_form(self, doctype=None):
        d = frappe.get_doc("Customize Form")
        if doctype:
            d.doc_type = doctype
        d.run_method("fetch_to_customize")
        return d
