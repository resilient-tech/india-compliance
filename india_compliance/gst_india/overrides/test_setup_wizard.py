import frappe
from frappe.tests.utils import FrappeTestCase


class TestSetupWizard(FrappeTestCase):
    def test_setup_wizard_with_valid_gstin(self):
        setup_company = "Wind Power LLP"
        company = frappe.get_doc("Company", setup_company)

        self.assertDocumentEqual(
            {"gst_category": "Unregistered", "gstin": None, "default_gst_rate": "18.0"},
            company,
        )

        self.assertEqual(
            frappe.db.get_single_value("Accounts Settings", "enable_audit_trail"), 0
        )
