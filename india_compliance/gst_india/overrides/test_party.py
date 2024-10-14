import frappe
from frappe.tests import IntegrationTestCase


class TestUtils(IntegrationTestCase):
    def test_validate_new_party(self):
        party = frappe.new_doc(
            "Customer", customer_name="Resilient Tech", gstin="24AUTPV8831F1ZZ"
        )
        party.save()

        self.assertEqual(party.gst_category, "Registered Regular")

    def test_validate_deemed_export_party(self):
        party = frappe.new_doc(
            "Customer",
            customer_name="Resilient Tech",
            gstin="24AUTPV8831F1ZZ",
            gst_category="Deemed Export",
        )
        party.save()

        self.assertEqual(party.gst_category, "Deemed Export")

    def test_validate_new_party_with_tcs(self):
        # Allow TCS GSTIN
        party = frappe.new_doc(
            "Customer",
            customer_name="Flipkart India Private Limited",
            gstin="29AABCF8078M1C8",
        )

        party.insert()
