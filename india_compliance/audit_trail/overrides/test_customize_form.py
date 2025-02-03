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

    def get_customize_form(self, doctype=None):
        d = frappe.get_doc("Customize Form")
        if doctype:
            d.doc_type = doctype
        d.run_method("fetch_to_customize")
        return d
