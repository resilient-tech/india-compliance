import frappe
<<<<<<< HEAD
from frappe.tests.utils import FrappeTestCase


class TestUtils(FrappeTestCase):
    def test_validate_new_party(self):
        party = frappe.new_doc("Customer")
        party.update({"customer_name": "Resilient Tech", "gstin": "24AUTPV8831F1ZZ"})
=======
from frappe.tests import IntegrationTestCase


class TestUtils(IntegrationTestCase):
    def test_validate_new_party(self):
        party = frappe.new_doc(
            "Customer", customer_name="Resilient Tech", gstin="24AUTPV8831F1ZZ"
        )
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)
        party.save()

        self.assertEqual(party.gst_category, "Registered Regular")

    def test_validate_deemed_export_party(self):
<<<<<<< HEAD
        party = frappe.new_doc("Customer")
        party.update(
            {
                "customer_name": "Resilient Tech",
                "gstin": "24AUTPV8831F1ZZ",
                "gst_category": "Deemed Export",
            }
=======
        party = frappe.new_doc(
            "Customer",
            customer_name="Resilient Tech",
            gstin="24AUTPV8831F1ZZ",
            gst_category="Deemed Export",
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)
        )
        party.save()

        self.assertEqual(party.gst_category, "Deemed Export")

    def test_validate_new_party_with_tcs(self):
        # Allow TCS GSTIN
<<<<<<< HEAD
        party = frappe.new_doc("Customer")
        party.update(
            {
                "customer_name": "Flipkart India Private Limited",
                "gstin": "29AABCF8078M1C8",
            }
=======
        party = frappe.new_doc(
            "Customer",
            customer_name="Flipkart India Private Limited",
            gstin="29AABCF8078M1C8",
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)
        )

        party.insert()
