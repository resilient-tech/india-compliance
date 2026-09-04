# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.report.gstin_status.gstin_status import execute


class TestGSTINStatus(IntegrationTestCase):
    GSTIN = "24AABCR6898M1ZN"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # the report reads the cached status, which is only populated by the GSTIN API
        frappe.get_doc(
            {
                "doctype": "GSTIN",
                "gstin": cls.GSTIN,
                "status": "Active",
                "registration_date": frappe.utils.getdate(),
                "is_blocked": 0,
            }
        ).insert(ignore_if_duplicate=True, ignore_mandatory=True)

    def run_report(self, **filters):
        _columns, data = execute(frappe._dict(filters))
        return data

    def test_lists_both_party_types(self):
        rows = self.run_report()

        self.assertTrue(rows)
        self.assertEqual({"Customer", "Supplier"}, {row["party_type"] for row in rows})

    def test_party_type_filter(self):
        rows = self.run_report(party_type="Supplier")

        self.assertTrue(rows)
        self.assertEqual({"Supplier"}, {row["party_type"] for row in rows})

    def test_status_filter(self):
        rows = self.run_report(status="Active")

        self.assertTrue(rows)
        self.assertEqual({"Active"}, {row["status"] for row in rows})
        self.assertIn(self.GSTIN, {row["gstin"] for row in rows})

    def test_invalid_party_type_filter(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Party Type must be either"):
            self.run_report(party_type="Employee")
