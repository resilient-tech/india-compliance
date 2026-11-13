import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.overrides.cross_app_hsn_code import before_update


class TestCrossAppHSNCode(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(frappe.flags.pop, "cross_app_hsn_code", None)

    def test_doctype_without_hsn_field_is_skipped(self):
        before_update(frappe.new_doc("ToDo"))
        self.assertFalse(frappe.flags.get("cross_app_hsn_code"))

    def test_hsn_code_is_passed_on_to_the_item(self):
        doc = frappe.new_doc("ToDo")
        doc.gst_hsn_code = "999900"
        before_update(doc)
        self.assertEqual(frappe.flags.cross_app_hsn_code, "999900")
