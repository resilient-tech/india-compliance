# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

import re

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from india_compliance.gst_india.utils.itc_claim import (
    ITC_CLAIM_PERIOD_DEFERRED,
    _calculate_itc_claim_period,
    _get_gst_fy_start,
    _get_next_unfiled_period,
    _get_section_16_4_deadline,
    _is_gstr3b_filed,
    _max_period,
    _next_period,
    _validate_period_format,
    compare_periods,
    format_period,
    get_itc_period_options,
    period_sort_key,
    period_to_date,
    update_gstr3b_filing_status,
)


class TestITCClaim(IntegrationTestCase):
    # =================================================================
    # Period Utility Functions
    # =================================================================

    def test_period_sort_key(self):
        # MMYYYY → YYYYMM conversion
        self.assertEqual(period_sort_key("012024"), "202401")
        self.assertEqual(period_sort_key("122023"), "202312")

        # ordering
        self.assertLess(period_sort_key("012024"), period_sort_key("022024"))
        self.assertLess(period_sort_key("122023"), period_sort_key("012024"))

    def test_compare_periods(self):
        self.assertEqual(compare_periods("012024", "012024"), 0)
        self.assertEqual(compare_periods("012024", "022024"), -1)
        self.assertEqual(compare_periods("022024", "012024"), 1)
        # cross-year
        self.assertEqual(compare_periods("122023", "012024"), -1)
        self.assertEqual(compare_periods("012024", "122023"), 1)

    def test_format_period(self):
        self.assertEqual(format_period(getdate("2024-01-15")), "012024")
        self.assertEqual(format_period("2024-12-01"), "122024")
        self.assertEqual(format_period("2024-09-15"), "092024")
        # same month, different days
        self.assertEqual(format_period("2024-03-01"), "032024")
        self.assertEqual(format_period("2024-03-31"), "032024")

    def test_period_to_date(self):
        self.assertEqual(period_to_date("012024"), getdate("2024-01-01"))
        self.assertEqual(period_to_date("012024", "last"), getdate("2024-01-31"))
        # leap year
        self.assertEqual(period_to_date("022024", "last"), getdate("2024-02-29"))
        self.assertEqual(period_to_date("022023", "last"), getdate("2023-02-28"))

    def test_period_to_date_invalid(self):
        for invalid in ("", "12345", "1234567"):
            with self.assertRaises(frappe.exceptions.ValidationError):
                period_to_date(invalid)

    def test_next_period(self):
        self.assertEqual(_next_period("012024"), "022024")
        self.assertEqual(_next_period("112024"), "122024")
        # year boundary
        self.assertEqual(_next_period("122023"), "012024")

        # 12 steps = 1 year
        period = "042023"
        for _ in range(12):
            period = _next_period(period)
        self.assertEqual(period, "042024")

    def test_max_period(self):
        self.assertEqual(_max_period("022024", "012024"), "022024")
        self.assertEqual(_max_period("012024", "022024"), "022024")
        self.assertEqual(_max_period("012024", "012024"), "012024")
        self.assertEqual(_max_period("122023", "012024"), "012024")

    def test_validate_period_format(self):
        # valid
        for p in ("012024", "122023", ITC_CLAIM_PERIOD_DEFERRED):
            _validate_period_format(p)  # should not raise

        # invalid
        invalid_periods = [
            "1320",
            "132024",
            "002024",
            "12-2024",
            "Dec2024",
            "MMYYYY",
            "abcdef",
            "12 2024",
        ]
        for invalid_period in invalid_periods:
            with self.assertRaisesRegex(
                frappe.exceptions.ValidationError,
                re.compile(r"ITC Claim Period '.*' must be in MMYYYY format"),
            ):
                _validate_period_format(invalid_period)

    # =================================================================
    # GST Fiscal Year Functions
    # =================================================================

    def test_get_gst_fy_start(self):
        # April onwards → same year
        self.assertEqual(_get_gst_fy_start("2024-04-01"), getdate("2024-04-01"))
        self.assertEqual(_get_gst_fy_start("2024-12-31"), getdate("2024-04-01"))
        # Jan-March → previous year
        self.assertEqual(_get_gst_fy_start("2025-01-01"), getdate("2024-04-01"))
        self.assertEqual(_get_gst_fy_start("2025-03-31"), getdate("2024-04-01"))

    def test_get_section_16_4_deadline(self):
        # Apr-Dec 2024 → November 2025
        self.assertEqual(_get_section_16_4_deadline("2024-04-01"), "112025")
        self.assertEqual(_get_section_16_4_deadline("2024-12-31"), "112025")
        # Jan-Mar 2025 → November 2025
        self.assertEqual(_get_section_16_4_deadline("2025-01-15"), "112025")
        self.assertEqual(_get_section_16_4_deadline("2025-03-31"), "112025")
        # March 2024 → November 2024
        self.assertEqual(_get_section_16_4_deadline("2024-03-15"), "112024")

    # =================================================================
    # Next Unfiled Period
    # =================================================================

    def test_get_next_unfiled_period_first_unfiled(self):
        result = _get_next_unfiled_period("24AAQCA8719H1ZC", "042024", "2024-04-01", filed=set())
        self.assertEqual(result, "042024")

    def test_get_next_unfiled_period_skips_filed(self):
        result = _get_next_unfiled_period(
            "24AAQCA8719H1ZC", "042024", "2024-04-01", filed={"042024", "052024"}
        )
        self.assertEqual(result, "062024")

    def test_get_next_unfiled_period_all_filed(self):
        filed = set()
        current = "042024"
        while compare_periods(current, "112025") <= 0:
            filed.add(current)
            current = _next_period(current)

        result = _get_next_unfiled_period("24AAQCA8719H1ZC", "042024", "2024-04-01", filed)
        self.assertIsNone(result)

    def test_get_next_unfiled_period_past_deadline(self):
        result = _get_next_unfiled_period("24AAQCA8719H1ZC", "122025", "2024-04-01", filed=set())
        self.assertIsNone(result)

    def test_get_next_unfiled_period_at_deadline(self):
        result = _get_next_unfiled_period("24AAQCA8719H1ZC", "112025", "2024-04-01", filed=set())
        self.assertEqual(result, "112025")

    # =================================================================
    # GSTR-3B Filing Status (Document Workflow)
    # =================================================================

    def test_update_gstr3b_filing_status(self):
        company_gstin = "24AAQCA8719H1ZC"

        # monthly
        update_gstr3b_filing_status(
            company_gstin=company_gstin,
            month_or_quarter="April",
            year=2020,
            status="Not Filed",
        )
        self.assertEqual(
            frappe.db.get_value(
                "GST Return Log",
                {
                    "gstin": company_gstin,
                    "return_period": "042020",
                    "return_type": "GSTR3B",
                },
                "filing_status",
            ),
            "Not Filed",
        )

        # toggle to Filed
        update_gstr3b_filing_status(
            company_gstin=company_gstin,
            month_or_quarter="April",
            year=2020,
            status="Filed",
        )
        self.assertEqual(
            frappe.db.get_value(
                "GST Return Log",
                {
                    "gstin": company_gstin,
                    "return_period": "042020",
                    "return_type": "GSTR3B",
                },
                "filing_status",
            ),
            "Filed",
        )

        # quarterly
        update_gstr3b_filing_status(
            company_gstin=company_gstin,
            month_or_quarter="Apr - Jun",
            year=2021,
            status="Filed",
        )
        self.assertEqual(
            frappe.db.get_value(
                "GST Return Log",
                {
                    "gstin": company_gstin,
                    "return_period": "062021",
                    "return_type": "GSTR3B",
                },
                "filing_status",
            ),
            "Filed",
        )

    # =================================================================
    # ITC Period Options (Document Workflow)
    # =================================================================

    def test_get_itc_period_options(self):
        company_gstin = "24AAQCA8719H1ZC"
        today = getdate()

        periods = get_itc_period_options(
            company_gstin=company_gstin,
            posting_date=str(today),
        )

        self.assertGreater(len(periods), 0)
        self.assertEqual(periods[0], ITC_CLAIM_PERIOD_DEFERRED)

        # Filed period should be excluded
        month_or_quarter = today.strftime("%B")
        year = today.year

        update_gstr3b_filing_status(
            company_gstin=company_gstin,
            month_or_quarter=month_or_quarter,
            year=year,
            status="Filed",
        )

        periods = get_itc_period_options(
            company_gstin=company_gstin,
            posting_date=str(today),
        )

        current_period = f"{today.month:02}{today.year}"
        self.assertNotIn(current_period, periods)

        # cleanup
        update_gstr3b_filing_status(
            company_gstin=company_gstin,
            month_or_quarter=month_or_quarter,
            year=year,
            status="Not Filed",
        )

    def test_get_itc_period_options_empty_inputs(self):
        self.assertEqual(get_itc_period_options(), [])
        self.assertEqual(get_itc_period_options(company_gstin="24AAQCA8719H1ZC"), [])
        self.assertEqual(get_itc_period_options(posting_date="2024-01-01"), [])

    # =================================================================
    # _is_gstr3b_filed
    # =================================================================

    def test_is_gstr3b_filed_deferred(self):
        """Deferred always returns False (never considered filed)."""
        self.assertFalse(_is_gstr3b_filed("24AAQCA8719H1ZC", ITC_CLAIM_PERIOD_DEFERRED))

    def test_is_gstr3b_filed_none_or_empty(self):
        """None / empty period always returns False."""
        self.assertFalse(_is_gstr3b_filed("24AAQCA8719H1ZC", None))
        self.assertFalse(_is_gstr3b_filed("24AAQCA8719H1ZC", ""))

    # =================================================================
    # _calculate_itc_claim_period — all branches
    # =================================================================

    def _make_doc(self, **overrides):
        """Return a simple dict-like object for _calculate_itc_claim_period."""
        defaults = frappe._dict(
            posting_date=getdate("2024-01-15"),
            company_gstin="24AAQCA8719H1ZC",
            itc_claim_period="",
        )
        defaults.update(overrides)
        return defaults

    def test_calc_skip_when_current_period_filed(self):
        """If current period is in filed set → return None (no update)."""
        doc = self._make_doc(itc_claim_period="012024")
        result = _calculate_itc_claim_period(doc, filed={"012024"})
        self.assertIsNone(result)

    def test_calc_ims_rejected(self):
        """IMS Rejected → Deferred."""
        doc = self._make_doc(itc_claim_period="012024")
        result = _calculate_itc_claim_period(doc, ims_action="Rejected")
        self.assertEqual(result, ITC_CLAIM_PERIOD_DEFERRED)

    def test_calc_ims_pending(self):
        """IMS Pending → Deferred."""
        doc = self._make_doc(itc_claim_period="012024")
        result = _calculate_itc_claim_period(doc, ims_action="Pending")
        self.assertEqual(result, ITC_CLAIM_PERIOD_DEFERRED)

    def test_calc_ims_accepted(self):
        """IMS Accepted → ims_period."""
        doc = self._make_doc(itc_claim_period="012024")
        result = _calculate_itc_claim_period(doc, ims_action="Accepted", ims_period="122024")
        self.assertEqual(result, "122024")

    def test_calc_inward_supply_rejected(self):
        """Matched inward supply with ims_action Rejected → Deferred."""
        doc = self._make_doc()
        inward = frappe._dict(ims_action="Rejected", return_period_2b="012024")
        result = _calculate_itc_claim_period(doc, inward_supply=inward)
        self.assertEqual(result, ITC_CLAIM_PERIOD_DEFERRED)

    def test_calc_inward_supply_pending(self):
        """Matched inward supply with ims_action Pending → Deferred."""
        doc = self._make_doc()
        inward = frappe._dict(ims_action="Pending", return_period_2b="012024")
        result = _calculate_itc_claim_period(doc, inward_supply=inward)
        self.assertEqual(result, ITC_CLAIM_PERIOD_DEFERRED)

    def test_calc_2b_period_later_than_posting(self):
        """2B period > posting → uses 2B period as start."""
        doc = self._make_doc(posting_date=getdate("2024-01-15"))
        inward = frappe._dict(ims_action="No Action", return_period_2b="032024")
        result = _calculate_itc_claim_period(doc, inward_supply=inward, filed=set())
        self.assertEqual(result, "032024")

    def test_calc_2b_period_earlier_than_posting(self):
        """2B period < posting → uses posting period as start."""
        doc = self._make_doc(posting_date=getdate("2024-03-15"))
        inward = frappe._dict(ims_action="No Action", return_period_2b="012024")
        result = _calculate_itc_claim_period(doc, inward_supply=inward, filed=set())
        self.assertEqual(result, "032024")

    def test_calc_unregistered_rcm(self):
        """Unregistered RCM always returns posting period."""
        doc = self._make_doc(
            gst_category="Unregistered",
            is_reverse_charge=1,
            posting_date=getdate("2024-01-15"),
        )
        result = _calculate_itc_claim_period(doc, filed=set())
        self.assertEqual(result, "012024")

    def test_calc_no_inward_supply(self):
        """No inward supply → uses posting period as start."""
        doc = self._make_doc(posting_date=getdate("2024-01-15"))
        result = _calculate_itc_claim_period(doc, filed=set())
        self.assertEqual(result, "012024")

    def test_calc_skips_filed_periods(self):
        """Filed periods are skipped to find next unfiled."""
        doc = self._make_doc(posting_date=getdate("2024-01-15"))
        result = _calculate_itc_claim_period(doc, filed={"012024", "022024"})
        self.assertEqual(result, "032024")

    def test_calc_ims_rejected_does_not_override_filed(self):
        """Filed check takes priority — even IMS Rejected cannot change a filed period."""
        doc = self._make_doc(itc_claim_period="012024")
        result = _calculate_itc_claim_period(doc, filed={"012024"}, ims_action="Rejected")
        # filed period is locked — returns None (no update)
        self.assertIsNone(result)
