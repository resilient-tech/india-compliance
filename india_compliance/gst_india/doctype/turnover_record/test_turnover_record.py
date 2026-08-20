# Copyright (c) 2026, Resilient Tech and contributors
# See license.txt

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe.tests import IntegrationTestCase
from frappe.utils import add_months, add_years, getdate, today

from india_compliance.gst_india.doctype.turnover_record.turnover_record import (
    get_relevant_period,
    get_turnover_amount,
    upsert_turnover_record,
)

FROM_DATE = "2024-04-01"
TO_DATE = "2025-03-31"
GUJARAT_GSTIN = "24AAQCA8719H1ZC"  # the Gujarat GSTIN of _Test Indian Registered Company
COMPANY = "_Test Indian Registered Company"
OTHER_COMPANY = "_Test ISD Branch Company"


def make_turnover_record(
    gst_state, amount, gstin=None, from_date=FROM_DATE, to_date=TO_DATE, company=COMPANY
):
    return frappe.get_doc(
        {
            "doctype": "Turnover Record",
            "from_date": from_date,
            "to_date": to_date,
            "company": company,
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

    def test_each_company_keeps_its_own_turnover_for_a_state(self):
        """Two companies can each have a branch in Gujarat. Keyed on the state alone the second
        overwrites the first, and both then divide the wrong pool. A company may also hold several
        ISD registrations, so the company -- not the distributing GSTIN -- owns these figures."""
        from_date, to_date = get_relevant_period(today())
        for company, amount in ((COMPANY, 500000), (OTHER_COMPANY, 800000)):
            record = make_turnover_record(
                "Tripura", amount, from_date=from_date, to_date=to_date, company=company
            )
            self.addCleanup(frappe.delete_doc, "Turnover Record", record.name, force=True)

        self.assertEqual(get_turnover_amount(COMPANY, "Tripura", today()), 500000)
        self.assertEqual(get_turnover_amount(OTHER_COMPANY, "Tripura", today()), 800000)

        # and an upsert reaches the company it names, leaving the other alone
        upsert_turnover_record(OTHER_COMPANY, None, "Tripura", 850000, today())
        self.assertEqual(get_turnover_amount(OTHER_COMPANY, "Tripura", today()), 850000)
        self.assertEqual(get_turnover_amount(COMPANY, "Tripura", today()), 500000)

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
        self.assertEqual(get_turnover_amount(COMPANY, "Maharashtra", today()), 750000)

        # ... and a record filed for the distribution's own year is not picked up
        record = make_turnover_record("Goa", 900000, from_date=fy_start, to_date=fy_end)
        self.addCleanup(frappe.delete_doc, "Turnover Record", record.name, force=True)
        self.assertIsNone(get_turnover_amount(COMPANY, "Goa", today()))

    def test_lookup_resolves_a_record_filed_for_part_of_the_relevant_period(self):
        """validate_duplicate_record rejects a second record overlapping the first, so a part-period
        record *is* the record for that state. The lookup has to resolve it on the same terms the
        bulk distribution dialog does, or the two disagree about the same branch."""
        from_date, to_date = get_relevant_period(today())
        record = make_turnover_record(
            "Punjab", 250000, from_date=add_months(getdate(from_date), 6), to_date=to_date
        )
        self.addCleanup(frappe.delete_doc, "Turnover Record", record.name, force=True)

        # the full period cannot be filed alongside it ...
        self.assertRaisesRegex(
            frappe.ValidationError,
            "already exists",
            make_turnover_record,
            "Punjab",
            250000,
            from_date=from_date,
            to_date=to_date,
        )

        # ... so this is the only turnover Punjab has, and the lookup resolves it
        self.assertEqual(get_turnover_amount(COMPANY, "Punjab", today()), 250000)

    def test_upsert_updates_the_overlapping_record(self):
        """An exact-date lookup missed a part-period record, so the upsert fell through to an insert
        that validate_duplicate_record rejected — and the blanket except swallowed it, leaving the
        turnover silently unchanged."""
        from_date, _ = get_relevant_period(today())
        record = make_turnover_record(
            "Kerala", 100000, from_date=from_date, to_date=add_months(getdate(from_date), 3)
        )
        self.addCleanup(frappe.delete_doc, "Turnover Record", record.name, force=True)

        upsert_turnover_record(company=COMPANY, gstin=None, gst_state="Kerala", amount=450000)

        self.assertEqual(frappe.db.get_value("Turnover Record", record.name, "amount"), 450000)
        self.assertEqual(get_turnover_amount(COMPANY, "Kerala", today()), 450000)
        # and no second record was created behind a swallowed exception
        self.assertEqual(frappe.db.count("Turnover Record", {"gst_state": "Kerala"}), 1)
