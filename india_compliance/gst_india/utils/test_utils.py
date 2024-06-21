from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate


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

    @patch(
        "india_compliance.gst_india.utils.getdate", return_value=getdate("2023-06-20")
    )
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
