# Copyright (c) 2026, Resilient Tech and contributors
# See license.txt

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe.tests import IntegrationTestCase
from frappe.utils import add_years, getdate, today

from india_compliance.gst_india.doctype.turnover_record.turnover_record import (
    get_relevant_period,
    get_turnover_amount,
)

FROM_DATE = "2024-04-01"
TO_DATE = "2025-03-31"
GUJARAT_GSTIN = "24AAQCA8719H1ZC"  # the Gujarat GSTIN of _Test Indian Registered Company


def make_turnover_record(gst_state, amount, gstin=None, from_date=FROM_DATE, to_date=TO_DATE):
    return frappe.get_doc(
        {
            "doctype": "Turnover Record",
            "from_date": from_date,
            "to_date": to_date,
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

    def test_record_validations(self):
        # one record per state per period
        self.assertRaisesRegex(
            frappe.ValidationError, "already exists", make_turnover_record, "Gujarat", 100000
        )

        self.assertRaisesRegex(
            frappe.ValidationError,
            "already exists",
            make_turnover_record,
            "Gujarat",
            100000,
            from_date="2024-07-01",
            to_date="2024-09-30",
        )

        # ... while a period that does not overlap is a separate, legitimate record
        record = make_turnover_record("Gujarat", 100000, from_date="2023-04-01", to_date="2024-03-31")
        self.assertEqual(record.gst_state, "Gujarat")

        # a GSTIN belongs to the state its first two digits encode
        self.assertRaisesRegex(
            frappe.ValidationError,
            "does not match",
            make_turnover_record,
            "Maharashtra",
            100000,
            gstin=GUJARAT_GSTIN,
        )

    def test_relevant_period_is_the_preceding_financial_year(self):
        """Rule 39(1): the ratio is driven by the financial year *preceding* the distribution, not
        by the year of distribution, which is still running and would move the ratio every month."""
        _, fy_start, fy_end = get_fiscal_year(today())
        from_date, to_date = get_relevant_period(today())

        self.assertEqual(from_date, add_years(getdate(fy_start), -1))
        self.assertEqual(to_date, add_years(getdate(fy_end), -1))

        # the lookup resolves the record filed for that preceding period ...
        record = make_turnover_record("Maharashtra", 750000, from_date=from_date, to_date=to_date)
        self.addCleanup(frappe.delete_doc, "Turnover Record", record.name, force=True)
        self.assertEqual(get_turnover_amount("Maharashtra", today()), 750000)

        # ... and a record filed for the distribution's own year is not picked up
        self.assertIsNone(get_turnover_amount("Goa", today()))
