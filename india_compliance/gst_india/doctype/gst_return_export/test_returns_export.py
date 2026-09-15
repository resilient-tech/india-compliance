# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""Adapters (summary math, storage) and the tool's endpoints."""

from typing import ClassVar
from unittest.mock import patch

import frappe
from frappe import parse_json, read_file
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from india_compliance.gst_india.doctype.gst_return_export import gst_return_export as controller
from india_compliance.gst_india.doctype.gst_return_export.return_adapters import (
    SECTION_ORDER,
    TAX_FIELDS,
    GSTR2AAdapter,
    GSTR2BAdapter,
    ReturnAdapter,
    section_rank,
    sum_summaries,
)
from india_compliance.gst_india.doctype.gst_return_export.template_exporter import merge_raw
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    get_raw_return_data,
    store_raw_return_data,
)
from india_compliance.gst_india.utils import get_data_file_path
from india_compliance.gst_india.utils.gstr_2 import save_gstr_2a, save_gstr_2b
from india_compliance.gst_india.utils.gstr_utils import ReturnType

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
        self.assertEqual(section_rank("B2B"), 0)
        self.assertEqual(section_rank("TCS"), len(SECTION_ORDER) - 1)

    def test_section_rank_unknown_goes_last(self):
        self.assertEqual(section_rank("ZZZ"), len(SECTION_ORDER))

    def test_sum_summaries_sums_totals_and_itc(self):
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
        result = sum_summaries(summaries)
        self.assertEqual(result["totals"]["documents"], 3)
        self.assertEqual(result["totals"]["taxable_value"], 150.0)
        self.assertEqual(result["totals"]["igst"], 27.0)
        self.assertEqual(result["itc"], {"available": 18.0, "not_available": 9.0, "reversal": 0.0})

    def test_sum_summaries_itc_none_when_absent(self):
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
        self.assertIsNone(sum_summaries(summaries)["itc"])


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

    def test_totals_and_itc_summed(self):
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
        ranks = [section_rank(s["section"]) for s in sections]
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

        summaries = self.adapter.get_summaries([PERIOD_2B])
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["period"], PERIOD_2B)
        self.assertEqual(summaries[0]["totals"], stored["totals"])

    def test_sync_status_tracks_stored_payload(self):
        """Synced = raw stored; a month without raw is not synced."""
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

    def test_summary_has_no_itc_and_is_consistent(self):
        summary = self.adapter.compute_summary("032020")
        self.assertTrue(summary["sections"])
        self.assertIsNone(summary["itc"])
        self.assertEqual(summary["totals"]["documents"], sum(s["documents"] for s in summary["sections"]))

    def test_summary_reads_gov_keyed_notes(self):
        """Stored 2A raw keeps the portal's cdn/cdna keys; they must land as CDNR/CDNRA."""
        sections = {s["section"] for s in self.adapter.compute_summary("032020")["sections"]}
        self.assertIn("CDNR", sections)
        self.assertIn("CDNRA", sections)


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

    def test_summary_without_raw_is_not_served(self):
        """Cached summary with no raw is stale; picker says not synced, summary must agree."""
        period = "082024"
        raw = {"docdata": {"b2b": [{"ctin": GSTIN, "trdnm": "X", "inv": [{"inum": "I1"}]}]}}
        store_raw_return_data(GSTIN, ReturnType.GSTR2B.value, period, raw)
        adapter = GSTR2BAdapter(GSTIN)
        self.assertIsNotNone(adapter.build_and_store_summary(period))

        log_name = f"{ReturnType.GSTR2B.value}-{period}-{GSTIN}"
        frappe.db.delete("File", {"attached_to_doctype": "GST Return Log", "attached_to_name": log_name})
        frappe.db.set_value("GST Return Log", log_name, "raw_gov_data", None)

        self.assertEqual(adapter.get_summaries([period]), [])

    def test_new_raw_clears_cached_summary(self):
        """Recon stores raw through the same path; the cache must not outlive its payload."""
        period = "072024"
        raw = {"docdata": {"b2b": [{"ctin": GSTIN, "trdnm": "X", "inv": [{"inum": "I1"}]}]}}
        store_raw_return_data(GSTIN, ReturnType.GSTR2B.value, period, raw)
        self.assertIsNotNone(GSTR2BAdapter(GSTIN).build_and_store_summary(period))

        log_name = f"{ReturnType.GSTR2B.value}-{period}-{GSTIN}"
        self.assertTrue(frappe.db.get_value("GST Return Log", log_name, "section_summary"))

        store_raw_return_data(GSTIN, ReturnType.GSTR2B.value, period, raw)
        self.assertFalse(frappe.db.get_value("GST Return Log", log_name, "section_summary"))


class TestGSTReturnExportController(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.doc = frappe.get_doc("GST Return Export")

    def setUp(self):
        # routing tests, not permission tests; no-op the company gate
        patcher = patch("india_compliance.gst_india.utils.validate_company_gstin_access")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_get_summary_maps_return_type_and_delegates(self):
        """The UI label must reach the adapter as the enum value the logs are named with."""
        fake = {"sections": [], "totals": {}, "itc": None}
        with patch.object(ReturnAdapter, "get_range_summary", return_value=fake) as summary:
            result = self.doc.get_summary(GSTIN, "GSTR-2B", "2020-08-01", "2020-08-31")

        self.assertEqual(result, fake)
        self.assertTrue(summary.called)

    def test_sync_only_accepts_months_the_portal_can_serve(self):
        """Client months land in log names; junk and months past the cut-off are dropped."""
        today = "india_compliance.gst_india.doctype.purchase_reconciliation_tool.getdate"
        with (
            patch.object(controller, "is_job_enqueued", return_value=False),
            patch(today, return_value=getdate("2021-05-20")),
        ):
            result = self.doc.sync_return_data(
                GSTIN, "GSTR-2B", ["../etc", "132021", "", "072021"], "2021-03-01", "2021-08-01"
            )

        self.assertEqual(result["indicator"], "orange")

    def test_sync_skips_when_job_already_enqueued(self):
        with patch.object(controller, "is_job_enqueued", return_value=True):
            result = self.doc.sync_return_data(GSTIN, "GSTR-2B", ["082020"], "2020-08-01", "2020-08-31")
        self.assertIn("already in progress", result["message"])

    def test_sync_status_stops_at_the_portal_cut_off(self):
        """2B for a month exists from the 14th of the next; on 20 May, April is the newest."""
        today = "india_compliance.gst_india.doctype.purchase_reconciliation_tool.getdate"
        with patch(today, return_value=getdate("2021-05-20")):
            status = self.doc.get_sync_status(GSTIN, "GSTR-2B", "2021-03-01", "2021-08-01")
            with self.assertRaises(frappe.ValidationError):
                self.doc.get_sync_status(GSTIN, "GSTR-2B", "2021-05-01", "2021-08-01")

        self.assertEqual([p["period"] for p in status["periods"]], ["032021", "042021"])

    def test_range_starts_where_the_return_does(self):
        """2A exists from July 2017, 2B from July 2020; earlier months are never offered."""
        today = "india_compliance.gst_india.doctype.purchase_reconciliation_tool.getdate"
        with patch(today, return_value=getdate("2020-12-01")):
            status_2b = self.doc.get_sync_status(GSTIN, "GSTR-2B", "2019-01-01", "2020-09-30")
        status_2a = self.doc.get_sync_status(GSTIN, "GSTR-2A", "2017-01-01", "2017-08-31")

        self.assertEqual([p["period"] for p in status_2b["periods"]], ["072020", "082020", "092020"])
        self.assertEqual([p["period"] for p in status_2a["periods"]], ["072017", "082017"])

    def test_export_before_the_return_existed_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            controller.export_return_as_excel(GSTIN, "GSTR-2B", "2019-01-01", "2019-12-31")

    def _export_job_id(self, return_type, from_date, to_date):
        with patch.object(controller.frappe, "enqueue") as enqueue:
            controller.export_return_as_excel(GSTIN, return_type, from_date, to_date, "all")
        return enqueue.call_args.kwargs["job_id"]

    def test_export_jobs_are_keyed_on_the_months_and_the_return(self):
        """Dedupe must collapse the same request, and never two different ones."""
        august_2b = self._export_job_id("GSTR-2B", "2020-08-01", "2020-08-31")

        self.assertEqual(self._export_job_id("GSTR-2B", "2020-08-10", "2020-08-20"), august_2b)
        self.assertNotEqual(self._export_job_id("GSTR-2A", "2020-08-01", "2020-08-31"), august_2b)
        self.assertNotEqual(self._export_job_id("GSTR-2B", "2020-09-01", "2020-09-30"), august_2b)

    def test_sync_reports_nothing_to_sync(self):
        with (
            patch.object(controller, "is_job_enqueued", return_value=False),
            patch(
                "india_compliance.gst_india.doctype.purchase_reconciliation_tool"
                ".purchase_reconciliation_tool.get_periods_to_download",
                return_value=[],
            ),
        ):
            result = self.doc.sync_return_data(GSTIN, "GSTR-2B", ["082020"], "2020-08-01", "2020-08-31")
        self.assertEqual(result["indicator"], "orange")
