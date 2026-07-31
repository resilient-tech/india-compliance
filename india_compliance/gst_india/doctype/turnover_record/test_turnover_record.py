# Copyright (c) 2026, Resilient Tech and contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

FROM_DATE = "2024-04-01"
TO_DATE = "2025-03-31"
GUJARAT_GSTIN = "24AAQCA8719H1ZC"  # the Gujarat GSTIN of _Test Indian Registered Company


def make_turnover_record(gst_state, amount, gstin=None):
    return frappe.get_doc(
        {
            "doctype": "Turnover Record",
            "from_date": FROM_DATE,
            "to_date": TO_DATE,
            "gst_state": gst_state,
            "gstin": gstin,
            "amount": amount,
        }
    ).insert()


class TestTurnoverRecord(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Turnover Record generates its own name and allows one record per state per period, so a
        # test_records fixture would be re-inserted (and rejected) on every run: build it here
        frappe.db.delete("Turnover Record", {"from_date": FROM_DATE, "to_date": TO_DATE})
        cls.with_gstin = make_turnover_record("Gujarat", 500000, gstin=GUJARAT_GSTIN)
        cls.without_gstin = make_turnover_record("Karnataka", 300000)

    @classmethod
    def tearDownClass(cls):
        frappe.db.delete("Turnover Record", {"from_date": FROM_DATE, "to_date": TO_DATE})
        super().tearDownClass()

    def test_record_with_gstin(self):
        self.assertEqual(self.with_gstin.gstin, GUJARAT_GSTIN)
        self.assertEqual(self.with_gstin.gst_state, "Gujarat")

    def test_record_without_gstin(self):
        # gstin is optional; the record is keyed by state and period
        self.assertFalse(self.without_gstin.gstin)
        self.assertEqual(self.without_gstin.gst_state, "Karnataka")

    def test_duplicate_record_for_same_state_and_period(self):
        self.assertRaises(frappe.ValidationError, make_turnover_record, "Gujarat", 100000)
