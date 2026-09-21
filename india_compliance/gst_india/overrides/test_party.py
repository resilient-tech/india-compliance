import frappe
from frappe.tests.utils import FrappeTestCase


class TestUtils(FrappeTestCase):
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
        """An OIDAR GSTIN is a non-resident registration: Overseas, and it carries no PAN"""
        party = frappe.new_doc(
            "Supplier",
            supplier_name="Google Asia Pacific Pte Ltd",
            country="Singapore",
            gstin="9917SGP29001OST",
        )
        party.insert()

        self.assertEqual(party.gst_category, "Overseas")
        self.assertEqual(party.pan, "")

    def test_transporter_pan_must_match_gstin(self):
        """PAN comparison holds even for GSTIN formats whose characters 3-12 are not a PAN"""

        def _transporter(name, gstin, transporter_id):
            return frappe.new_doc(
                "Supplier",
                supplier_name=name,
                supplier_type="Company",
                is_transporter=1,
                gstin=gstin,
                gst_transporter_id=transporter_id,
            )

        # both slices are valid PANs, and they differ
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            "doesn't match the PAN extracted from GSTIN",
            _transporter("_Test Transporter PAN A", "24AAUPV7468F1ZW", "29AABCF8078M1ZX").insert,
        )

        # OIDAR GSTIN yields no PAN, so it still cannot match a real one
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            "doesn't match the PAN extracted from GSTIN",
            _transporter("_Test Transporter PAN B", "9917SGP29001OST", "29AABCF8078M1ZX").insert,
        )

        # neither slice is a PAN: the PAN check cannot distinguish them, but the
        # transporter ID format check still rejects the document
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            "doesn't match the required format",
            _transporter("_Test Transporter PAN C", "0717UNO00157UNO", "0717UNO00211UN2").insert,
        )

    def test_oidar_gstin_on_address_does_not_set_pan(self):
        """Address hook backfills an Unregistered party, and must not store a non-PAN string"""
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
