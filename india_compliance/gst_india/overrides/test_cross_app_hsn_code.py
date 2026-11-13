import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.overrides.cross_app_hsn_code import before_update


class TestCrossAppHSNCode(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(frappe.flags.pop, "cross_app_hsn_code", None)

    def test_doctype_without_hsn_field_is_skipped(self):
        # ToDo stands in for a Healthcare doctype before India Compliance adds gst_hsn_code
        doc = frappe.new_doc("ToDo")
        self.assertFalse(doc.meta.has_field("gst_hsn_code"))

        before_update(doc)
        self.assertFalse(frappe.flags.get("cross_app_hsn_code"))

    def test_hsn_code_is_passed_on_to_the_item(self):
        doc = frappe.new_doc("ToDo")
        doc.gst_hsn_code = "61149090"
        before_update(doc)

        item = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": "_Test Cross App HSN Item",
                "item_group": "All Item Groups",
                "stock_uom": "Nos",
            }
        ).insert()

        self.assertEqual(item.gst_hsn_code, "61149090")
        self.assertFalse(frappe.flags.get("cross_app_hsn_code"))
