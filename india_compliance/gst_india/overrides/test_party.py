import frappe
from frappe.tests import IntegrationTestCase


class TestUtils(IntegrationTestCase):
    def test_validate_new_party(self):
        party = frappe.new_doc("Customer", customer_name="Resilient Tech", gstin="24AUTPV8831F1ZZ")
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

    def test_validate_oidar_party(self):
        party = frappe.new_doc(
            "Supplier",
            supplier_name="Google Asia Pacific Pte Ltd",
            country="Singapore",
            gstin="9917SGP29001OST",
        )
        party.insert()

        self.assertEqual(party.gst_category, "Overseas")
        self.assertEqual(party.pan, "")

    def test_oidar_gstin_on_address_does_not_set_pan(self):
        party = frappe.new_doc(
            "Supplier",
            supplier_name="_Test OIDAR Backfill Supplier",
            supplier_type="Company",
        )
        party.insert()
        self.assertEqual(party.gst_category, "Unregistered")

        frappe.get_doc(
            {
                "doctype": "Address",
                "address_title": "_Test OIDAR Backfill",
                "address_type": "Billing",
                "address_line1": "70 Pasir Panjang Road",
                "city": "Singapore",
                "country": "Singapore",
                "gstin": "9917SGP29001OST",
                "gst_category": "Overseas",
                "links": [{"link_doctype": "Supplier", "link_name": party.name}],
            }
        ).insert()

        party.reload()
        self.assertEqual(party.gstin, "9917SGP29001OST")
        self.assertEqual(party.gst_category, "Overseas")
        self.assertEqual(party.pan, "")
