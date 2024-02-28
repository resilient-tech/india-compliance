import re

import frappe
from frappe.custom.doctype.customize_form.test_customize_form import TestCustomizeForm


class TestCustomizeFormAuditTrail(TestCustomizeForm):
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
