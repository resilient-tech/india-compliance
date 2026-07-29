# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""
Tests for the GST Return Export ports-and-adapters layer (returns_export) and the
doctype controller: pure unit tests for the aggregation logic, integration tests for
compute_summary / storage over the shipped fixtures, and the controller endpoints.
"""

from typing import ClassVar
from unittest.mock import patch

import frappe
from frappe import parse_json, read_file
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from india_compliance.gst_india.doctype.gst_return_export import gst_return_export as controller
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    get_raw_return_data,
    store_raw_return_data,
)
from india_compliance.gst_india.utils import get_data_file_path
from india_compliance.gst_india.utils.gstr_2 import save_gstr_2a, save_gstr_2b
from india_compliance.gst_india.utils.gstr_utils import ReturnType
from india_compliance.gst_india.utils.returns_export import (
    SECTION_ORDER,
    TAX_FIELDS,
    GSTR2AAdapter,
    GSTR2BAdapter,
    ReturnAdapter,
    _cumulate,
    _section_rank,
    merge_raw,
)

GSTIN = "01AABCE2207R1Z5"
PERIOD_2B = "032020"


class TestMergeRaw(IntegrationTestCase):
    def test_lists_concatenate(self):
        self.assertEqual(merge_raw({"b2b": [1]}, {"b2b": [2, 3]}), {"b2b": [1, 2, 3]})

    def test_numbers_add(self):
        self.assertEqual(merge_raw({"igst": 5}, {"igst": 3}), {"igst": 8})

    def test_dicts_recurse(self):
        self.assertEqual(
            merge_raw({"a": {"x": [1], "n": 2}}, {"a": {"x": [2], "n": 3, "y": 9}}),
            {"a": {"x": [1, 2], "n": 5, "y": 9}},
        )

    def test_itcsumm_numbers_sum_deeply(self):
        self.assertEqual(
            merge_raw({"itcsumm": {"itcavl": {"igst": 10}}}, {"itcsumm": {"itcavl": {"igst": 5}}}),
            {"itcsumm": {"itcavl": {"igst": 15}}},
        )

    def test_new_key_added_and_scalar_newer_wins(self):
        self.assertEqual(merge_raw({"a": "x"}, {"a": "y", "b": 1}), {"a": "y", "b": 1})

    def test_empty_existing_returns_new(self):
        self.assertEqual(merge_raw({}, {"b2b": [1]}), {"b2b": [1]})

    def test_null_does_not_clobber_accumulated_data(self):
        self.assertEqual(merge_raw({"b2b": [1, 2]}, {"b2b": None}), {"b2b": [1, 2]})


class TestSummaryHelpers(IntegrationTestCase):
    def test_section_rank_orders_known_sections(self):
        self.assertEqual(_section_rank("B2B"), 0)
        self.assertEqual(_section_rank("IMPGSEZ"), len(SECTION_ORDER) - 1)

    def test_section_rank_unknown_goes_last(self):
        self.assertEqual(_section_rank("ZZZ"), len(SECTION_ORDER))

    def test_cumulate_sums_totals_and_itc(self):
        summaries = [
            {
                "totals": {
                    "documents": 2,
                    "taxable_value": 100.0,
                    "igst": 18.0,
                    "cgst": 0.0,
                    "sgst": 0.0,
                    "cess": 0.0,
                },
                "itc": {"available": 18.0, "not_available": 0.0, "reversal": 0.0},
            },
            {
                "totals": {
                    "documents": 1,
                    "taxable_value": 50.0,
                    "igst": 9.0,
                    "cgst": 0.0,
                    "sgst": 0.0,
                    "cess": 0.0,
                },
                "itc": {"available": 0.0, "not_available": 9.0, "reversal": 0.0},
            },
        ]
        result = _cumulate(summaries)
        self.assertEqual(result["totals"]["documents"], 3)
        self.assertEqual(result["totals"]["taxable_value"], 150.0)
        self.assertEqual(result["totals"]["igst"], 27.0)
        self.assertEqual(result["itc"], {"available": 18.0, "not_available": 9.0, "reversal": 0.0})

    def test_cumulate_itc_none_when_absent(self):
        summaries = [
            {
                "totals": {
                    "documents": 1,
                    "taxable_value": 10.0,
                    "igst": 1.0,
                    "cgst": 0.0,
                    "sgst": 0.0,
                    "cess": 0.0,
                },
                "itc": None,
            }
        ]
        self.assertIsNone(_cumulate(summaries)["itc"])


class TestRangeSummary(IntegrationTestCase):
    """get_range_summary driven by crafted stored summaries (no DB)."""

    STORED: ClassVar = [
        {
            "period": "042024",
            "sections": [
                {
                    "section": "B2B",
                    "documents": 2,
                    "taxable_value": 100.0,
                    "igst": 18.0,
                    "cgst": 0.0,
                    "sgst": 0.0,
                    "cess": 0.0,
                }
            ],
            "totals": {
                "documents": 2,
                "taxable_value": 100.0,
                "igst": 18.0,
                "cgst": 0.0,
                "sgst": 0.0,
                "cess": 0.0,
            },
            "itc": {"available": 18.0, "not_available": 0.0, "reversal": 0.0},
            "last_updated_on": "2024-05-01 10:00:00",
        },
        {
            "period": "052024",
            "sections": [
                {
                    "section": "B2B",
                    "documents": 1,
                    "taxable_value": 50.0,
                    "igst": 9.0,
                    "cgst": 0.0,
                    "sgst": 0.0,
                    "cess": 0.0,
                },
                {
                    "section": "CDNR",
                    "documents": 1,
                    "taxable_value": 20.0,
                    "igst": 3.6,
                    "cgst": 0.0,
                    "sgst": 0.0,
                    "cess": 0.0,
                },
            ],
            "totals": {
                "documents": 2,
                "taxable_value": 70.0,
                "igst": 12.6,
                "cgst": 0.0,
                "sgst": 0.0,
                "cess": 0.0,
            },
            "itc": {"available": 12.6, "not_available": 0.0, "reversal": 0.0},
            "last_updated_on": "2024-06-01 10:00:00",
        },
    ]

    def _range(self, periods):
        with patch.object(ReturnAdapter, "get_summaries", return_value=self.STORED):
            return GSTR2BAdapter(GSTIN).get_range_summary(periods)

    def test_sections_summed_across_months_with_breakdown(self):
        sections = self._range(["042024", "052024", "062024"])["sections"]
        self.assertEqual([s["section"] for s in sections], ["B2B", "CDNR"])
        b2b = sections[0]
        self.assertEqual(b2b["documents"], 3)
        self.assertEqual(b2b["taxable_value"], 150.0)
        self.assertEqual(b2b["igst"], 27.0)
        self.assertEqual([m["period"] for m in b2b["months"]], ["042024", "052024"])

    def test_totals_and_itc_cumulated(self):
        result = self._range(["042024", "052024"])
        self.assertEqual(result["totals"]["documents"], 4)
        self.assertEqual(result["totals"]["taxable_value"], 170.0)
        self.assertAlmostEqual(result["totals"]["igst"], 30.6)
        self.assertAlmostEqual(result["itc"]["available"], 30.6)


class TestComputeSummary2B(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        data = parse_json(read_file(get_data_file_path("test_gstr_2b_v4_0.json")))
        save_gstr_2b(GSTIN, PERIOD_2B, data)
        cls.adapter = GSTR2BAdapter(GSTIN)

    def test_sections_and_totals_are_consistent(self):
        summary = self.adapter.compute_summary(PERIOD_2B)
        sections = summary["sections"]
        self.assertTrue(sections)
        self.assertEqual(summary["totals"]["documents"], sum(s["documents"] for s in sections))
        for tax in TAX_FIELDS:
            self.assertAlmostEqual(summary["totals"][tax], sum(s[tax] for s in sections))
        ranks = [_section_rank(s["section"]) for s in sections]
        self.assertEqual(ranks, sorted(ranks))

    def test_itc_buckets_partition_total_tax(self):
        summary = self.adapter.compute_summary(PERIOD_2B)
        itc = summary["itc"]
        self.assertIsNotNone(itc)
        total_tax = sum(summary["totals"][t] for t in TAX_FIELDS)
        self.assertAlmostEqual(itc["available"] + itc["not_available"] + itc["reversal"], total_tax)

    def test_build_and_store_then_get_summaries_round_trip(self):
        stored = self.adapter.build_and_store_summary(PERIOD_2B)
        self.assertIsNotNone(stored)
        self.assertIn("last_updated_on", stored)

        summaries = self.adapter.get_summaries([PERIOD_2B])
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["period"], PERIOD_2B)
        self.assertEqual(summaries[0]["totals"], stored["totals"])

    def test_sync_status_tracks_stored_payload(self):
        """A month is synced only when its raw payload (`filed`) is stored — save_gstr_2b
        stored PERIOD_2B, an untouched month is missing (so an old download that never
        stored a payload is reported as not synced, not a false positive)."""
        self.adapter.build_and_store_summary(PERIOD_2B)
        status = self.adapter.get_sync_status([PERIOD_2B, "011999"])
        by_period = {p["period"]: p for p in status["periods"]}

        self.assertTrue(by_period[PERIOD_2B]["synced"])
        self.assertIsNotNone(by_period[PERIOD_2B]["last_updated_on"])
        self.assertFalse(by_period["011999"]["synced"])
        self.assertTrue(status["has_missing_sync"])


class TestComputeSummary2A(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        data = parse_json(read_file(get_data_file_path("test_gstr_2a.json")))
        save_gstr_2a(GSTIN, "032020", data.copy())
        cls.adapter = GSTR2AAdapter(GSTIN)
        cls.period = frappe.db.get_value(
            "GST Inward Supply",
            {"company_gstin": GSTIN, "is_downloaded_from_2a": 1, "sup_return_period": ("is", "set")},
            "sup_return_period",
        )

    def test_summary_has_no_itc_and_is_consistent(self):
        self.assertIsNotNone(self.period)
        summary = self.adapter.compute_summary(self.period)
        self.assertTrue(summary["sections"])
        self.assertIsNone(summary["itc"])
        self.assertEqual(summary["totals"]["documents"], sum(s["documents"] for s in summary["sections"]))


class TestRawReturnDataRoundTrip(IntegrationTestCase):
    def test_store_get_and_overwrite(self):
        raw = {"b2b": [{"ctin": GSTIN}], "itcsumm": {"itcavl": {"igst": 10}}}
        store_raw_return_data(GSTIN, ReturnType.GSTR2B.value, "062024", raw)

        got = get_raw_return_data(GSTIN, ReturnType.GSTR2B.value, "062024")
        self.assertEqual(got["b2b"], [{"ctin": GSTIN}])
        self.assertEqual(got["itcsumm"], {"itcavl": {"igst": 10}})

        store_raw_return_data(GSTIN, ReturnType.GSTR2B.value, "062024", {"impg": [{"x": 1}]})
        replaced = get_raw_return_data(GSTIN, ReturnType.GSTR2B.value, "062024")
        self.assertNotIn("b2b", replaced)
        self.assertEqual(replaced["impg"], [{"x": 1}])

    def test_missing_period_returns_none(self):
        self.assertIsNone(get_raw_return_data(GSTIN, ReturnType.GSTR2B.value, "011999"))


class TestGSTReturnExportController(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.doc = frappe.get_doc("GST Return Export")

    def setUp(self):
        # These tests exercise routing/delegation, not GSTIN permissions; no-op the
        # company-gstin gate so they don't depend on a Company fixture (or test order).
        patcher = patch("india_compliance.gst_india.utils.validate_company_gstin_access")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_get_summary_maps_return_type_and_delegates(self):
        fake = {"periods": [], "sections": [], "totals": {}, "itc": None}
        with patch.object(ReturnAdapter, "get_range_summary", return_value=fake):
            result = self.doc.get_summary(GSTIN, "GSTR-2B", "2020-03-01", "2020-03-31")
        self.assertEqual(result["return_type"], ReturnType.GSTR2B.value)
        self.assertEqual(result["sections"], [])
        self.assertIn("totals", result)

    def test_sync_skips_when_job_already_enqueued(self):
        with patch.object(controller, "is_job_enqueued", return_value=True):
            result = self.doc.sync_return_data(GSTIN, "GSTR-2B", ["032020"])
        self.assertIn("already in progress", result["message"])

    def test_sync_status_stops_at_the_portal_cut_off(self):
        """2B for a month isn't generated until the 14th of the next one, so the picker
        must not offer months past `BaseUtil._getdate` — nor anything at all when the whole
        range is past it."""
        cut_off = "india_compliance.gst_india.doctype.purchase_reconciliation_tool.BaseUtil._getdate"
        with patch(cut_off, return_value=getdate("2020-05-20")):
            status = self.doc.get_sync_status(GSTIN, "GSTR-2B", "2020-03-01", "2020-08-01")
            future = self.doc.get_sync_status(GSTIN, "GSTR-2B", "2020-06-01", "2020-08-01")

        self.assertEqual([p["period"] for p in status["periods"]], ["032020", "042020", "052020"])
        self.assertEqual(future["periods"], [])
        self.assertFalse(future["has_missing_sync"])

    def test_sync_reports_nothing_to_sync(self):
        with (
            patch.object(controller, "is_job_enqueued", return_value=False),
            patch(
                "india_compliance.gst_india.doctype.purchase_reconciliation_tool"
                ".purchase_reconciliation_tool.get_periods_to_download",
                return_value=[],
            ),
        ):
            result = self.doc.sync_return_data(GSTIN, "GSTR-2B", ["032020"])
        self.assertEqual(result["indicator"], "orange")
