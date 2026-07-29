import re
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import frappe
<<<<<<< HEAD
from frappe.tests.utils import FrappeTestCase
=======
import time_machine
from frappe.tests import IntegrationTestCase, change_settings
>>>>>>> 4e695ae8 (fix: add test for is_ship_to_gstin_applicable rollover behavior in IST)
from frappe.utils import getdate

from india_compliance.gst_india.utils import is_ship_to_gstin_applicable, validate_pincode


class TestUtils(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # create old fiscal years
        fiscal_year = frappe.new_doc("Fiscal Year")
        fiscal_year.update(
            {
                "year_start_date": "2023-04-01",
                "year_end_date": "2024-03-31",
                "year": "2023-2024",
            }
        ).insert(ignore_if_duplicate=True)

        fiscal_year = frappe.new_doc("Fiscal Year")
        fiscal_year.update(
            {
                "year_start_date": "2022-04-01",
                "year_end_date": "2023-03-31",
                "year": "2022-2023",
            }
        ).insert(ignore_if_duplicate=True)

    @patch("india_compliance.gst_india.utils.getdate", return_value=getdate("2023-06-20"))
    def test_timespan_date_range(self, getdate_mock):
        from india_compliance.gst_india.utils import get_timespan_date_range

        timespan_date_range_map = {
            "this fiscal year": (date(2023, 4, 1), date(2024, 3, 31)),
            "last fiscal year": (date(2022, 4, 1), date(2023, 3, 31)),
            "this fiscal year to last month": (date(2023, 4, 1), date(2023, 5, 31)),
            "this quarter to last month": (date(2023, 4, 1), date(2023, 5, 31)),
        }

        for timespan, expected_date_range in timespan_date_range_map.items():
            actual_date_range = get_timespan_date_range(timespan)

            for i, expected_date in enumerate(expected_date_range):
                self.assertEqual(expected_date, actual_date_range[i])

    @change_settings("GST Settings", {"sandbox_mode": 0})
    def test_is_ship_to_gstin_applicable_rolls_over_in_ist(self):
        """NIC rolls over at midnight IST, whatever the site's own timezone is."""
        rollover = datetime(2026, 7, 31, 18, 30, tzinfo=timezone.utc)  # 2026-08-01 00:00 IST

        for time_zone in ("UTC", "Pacific/Kiritimati"):  # behind IST, then ahead of it
            with change_settings("System Settings", {"time_zone": time_zone}):
                with time_machine.travel(rollover - timedelta(minutes=1), tick=False):
                    self.assertFalse(is_ship_to_gstin_applicable(), time_zone)

                with time_machine.travel(rollover, tick=False):
                    self.assertTrue(is_ship_to_gstin_applicable(), time_zone)

    def test_validate_pincode(self):
        def make_address(state, pincode):
            return frappe._dict(country="India", state=state, pincode=pincode, __unsaved=True)

        for pincode in ("194101", "190015", "181101", "180007", "184101", "191401"):
            self.assertIsNone(validate_pincode(make_address("Ladakh", pincode)))
            self.assertIsNone(validate_pincode(make_address("Jammu and Kashmir", pincode)))

        for pincode in ("518503", "533347"):
            self.assertIsNone(validate_pincode(make_address("Telangana", pincode)))
            self.assertIsNone(validate_pincode(make_address("Andhra Pradesh", pincode)))

        self.assertIsNone(validate_pincode(make_address("Telangana", "500001")))

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Postal Code .* is not associated with .*)$"),
            validate_pincode,
            make_address("Karnataka", "500001"),
        )
