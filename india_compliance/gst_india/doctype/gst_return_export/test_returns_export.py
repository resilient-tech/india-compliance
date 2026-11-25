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
    ITC_REVERSAL_SECTION,
    SECTION_ORDER,
    GSTR2AAdapter,
    GSTR2BAdapter,
    ReturnAdapter,
    section_rank,
    section_totals,
)
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    get_raw_return_data,
    store_raw_return_data,
)
from india_compliance.gst_india.utils import get_data_file_path, merge_dicts
from india_compliance.gst_india.utils.gstr_2 import save_gstr_2a, save_gstr_2b
from india_compliance.gst_india.utils.gstr_utils import ReturnType
from india_compliance.gst_returns.fields.gstr2 import DocField as doc
from india_compliance.gst_returns.fields.gstr2 import RawField2b as raw2b

GSTIN = "01AABCE2207R1Z5"
PERIOD_2B = "032020"


class TestMergeMonths(IntegrationTestCase):
    def test_lists_concatenate(self):
        self.assertEqual(merge_dicts({"b2b": [1]}, {"b2b": [2, 3]}), {"b2b": [1, 2, 3]})

    def test_numbers_add(self):
        self.assertEqual(merge_dicts({"igst": 5}, {"igst": 3}), {"igst": 8})

    def test_dicts_recurse(self):
        self.assertEqual(
            merge_dicts({"a": {"x": [1], "n": 2}}, {"a": {"x": [2], "n": 3, "y": 9}}),
            {"a": {"x": [1, 2], "n": 5, "y": 9}},
        )

    def test_itcsumm_numbers_sum_deeply(self):
        self.assertEqual(
            merge_dicts({"itcsumm": {"itcavl": {"igst": 10}}}, {"itcsumm": {"itcavl": {"igst": 5}}}),
            {"itcsumm": {"itcavl": {"igst": 15}}},
        )

    def test_new_key_added_and_scalar_newer_wins(self):
        self.assertEqual(merge_dicts({"a": "x"}, {"a": "y", "b": 1}), {"a": "y", "b": 1})

    def test_empty_existing_returns_new(self):
        self.assertEqual(merge_dicts({}, {"b2b": [1]}), {"b2b": [1]})

    def test_null_does_not_clobber_accumulated_data(self):
        self.assertEqual(merge_dicts({"b2b": [1, 2]}, {"b2b": None}), {"b2b": [1, 2]})


class TestSummaryHelpers(IntegrationTestCase):
    def test_section_rank_orders_known_sections(self):
        self.assertEqual(section_rank("B2B"), 0)
        self.assertEqual(section_rank("TCS"), len(SECTION_ORDER) - 1)

    def test_section_rank_unknown_goes_last(self):
        self.assertEqual(section_rank("ZZZ"), len(SECTION_ORDER))

    def test_cdnr_totals_subtract_credit_notes(self):
        debit_note = {doc.DOC_TYPE: "Debit Note", "taxable_value": 100, "igst": 18}
        credit_note = {doc.DOC_TYPE: "Credit Note", "taxable_value": 300, "igst": 54}

        total = section_totals("CDNR", [debit_note, credit_note], subtract_credit_notes=True)
        self.assertEqual((total["documents"], total["taxable_value"], total["igst"]), (2, -200, -36))
        self.assertEqual((debit_note["taxable_value"], credit_note["taxable_value"]), (100, 300))

        credit_only = section_totals("CDNR", [credit_note], subtract_credit_notes=True)
        self.assertEqual((credit_only["taxable_value"], credit_only["igst"]), (-300, -54))

        b2b = section_totals("B2B", [credit_note], subtract_credit_notes=True)
        self.assertEqual((b2b["taxable_value"], b2b["igst"]), (300, 54))


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
            "itc_summary": {"available": 18.0, "not_available": 5.0, "reversal": 2.0},
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
            "itc_summary": {"available": -12.6, "not_available": 3.0, "reversal": 1.0},
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

    def test_itc_summed(self):
        itc = self._range(["042024", "052024"])["itc_summary"]
        self.assertAlmostEqual(itc["available"], 5.4)
        self.assertEqual((itc["not_available"], itc["reversal"]), (8.0, 3.0))

    def test_no_itc_when_no_month_has_it(self):
        stored = [{**summary, "itc_summary": None} for summary in self.STORED]
        with patch.object(ReturnAdapter, "get_summaries", return_value=stored):
            self.assertIsNone(GSTR2AAdapter(GSTIN).get_range_summary(["042024", "052024"])["itc_summary"])


class TestComputeSummary2B(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        data = parse_json(read_file(get_data_file_path("test_gstr_2b_v4_0.json")))
        save_gstr_2b(GSTIN, PERIOD_2B, data)
        cls.adapter = GSTR2BAdapter(GSTIN)

    def test_sections_come_in_portal_order(self):
        sections = self.adapter.compute_summary(PERIOD_2B)["sections"]
        self.assertTrue(sections)
        ranks = [section_rank(s["section"]) for s in sections]
        self.assertEqual(ranks, sorted(ranks))

    def test_itc_cards_show_the_portals_itc_summary(self):
        itc = self.adapter.compute_summary(PERIOD_2B)["itc_summary"]
        self.assertEqual(itc, {"available": 3600.0, "not_available": 9000.0, "reversal": 3600.0})

        documents = {"b2b": [{"ctin": GSTIN, "trdnm": "X", "inv": [{"inum": "I1"}]}]}
        itcsumm = {
            raw2b.ITC_AVAILABLE: {
                raw2b.NON_REVERSE_CHARGE_SUPPLIES: {"igst": 1000, "cgst": 100, "sgst": 100, "cess": 10},
                raw2b.ISD_SUPPLIES: {"igst": 2000},
                raw2b.REVERSE_CHARGE_SUPPLIES: {"igst": 4000},
                raw2b.IMPORTS: {"igst": 8000},
                raw2b.CREDIT_NOTES: {"igst": 300},
            },
            raw2b.ITC_NOT_AVAILABLE: {
                raw2b.NON_REVERSE_CHARGE_SUPPLIES: {"igst": 10},
                raw2b.ISD_SUPPLIES: {"igst": 20},
                raw2b.REVERSE_CHARGE_SUPPLIES: {"igst": 40},
                raw2b.IMPORTS: {"igst": 80},
                raw2b.CREDIT_NOTES: {"igst": 5},
            },
            raw2b.ITC_REVERSAL: {
                raw2b.NON_REVERSE_CHARGE_SUPPLIES: {"igst": 7},
                raw2b.ISD_SUPPLIES: {"igst": 70},
                raw2b.REVERSE_CHARGE_SUPPLIES: {"igst": 700},
                raw2b.IMPORTS: {"igst": 7000},
                raw2b.CREDIT_NOTES: {"igst": 70000},
            },
            raw2b.ITC_REJECTED: {
                raw2b.NON_REVERSE_CHARGE_SUPPLIES: {"igst": 100000},
                raw2b.CREDIT_NOTES: {"igst": 200000},
            },
        }
        store_raw_return_data(
            GSTIN, ReturnType.GSTR2B.value, "042020", {raw2b.DOC_DATA: documents, raw2b.ITC_SUMMARY: itcsumm}
        )
        self.assertEqual(
            self.adapter.compute_summary("042020")["itc_summary"],
            {"available": 14905.0, "not_available": 70.0, "reversal": 7.0},
        )

        credit_notes_exceed_invoices = {
            raw2b.ITC_AVAILABLE: {
                raw2b.NON_REVERSE_CHARGE_SUPPLIES: {"igst": 100},
                raw2b.CREDIT_NOTES: {"igst": 300},
            }
        }
        store_raw_return_data(
            GSTIN,
            ReturnType.GSTR2B.value,
            "052020",
            {raw2b.DOC_DATA: documents, raw2b.ITC_SUMMARY: credit_notes_exceed_invoices},
        )
        self.assertEqual(
            self.adapter.compute_summary("052020")["itc_summary"],
            {"available": -200.0, "not_available": 0.0, "reversal": 0.0},
        )
        self.assertEqual(
            self.adapter.get_range_summary(["042020", "052020"])["itc_summary"],
            {"available": 14705.0, "not_available": 70.0, "reversal": 7.0},
        )

    def test_reversal_documents_get_their_own_section(self):
        sections = {s["section"]: s for s in self.adapter.compute_summary(PERIOD_2B)["sections"]}
        self.assertEqual(sections[ITC_REVERSAL_SECTION]["documents"], 4)

    def test_a_reversal_only_month_still_has_a_summary(self):
        raw = get_raw_return_data(GSTIN, ReturnType.GSTR2B.value, PERIOD_2B)
        reversal_only = {**raw, raw2b.DOC_DATA: {raw2b.ITC_REVERSAL: raw[raw2b.DOC_DATA][raw2b.ITC_REVERSAL]}}
        store_raw_return_data(GSTIN, ReturnType.GSTR2B.value, "062020", reversal_only)
        sections = self.adapter.compute_summary("062020")["sections"]

        self.assertEqual([s["section"] for s in sections], [ITC_REVERSAL_SECTION])

    def test_reversal_amounts_add_up_from_rate_lines(self):
        raw = get_raw_return_data(GSTIN, ReturnType.GSTR2B.value, PERIOD_2B)
        supplier = raw[raw2b.DOC_DATA][raw2b.ITC_REVERSAL][0]["b2b"][0]
        rate_line = {raw2b.TAX_RATE: 18, raw2b.TAXABLE_VALUE: 1000, raw2b.IGST: 180}
        invoice = {**supplier[raw2b.INVOICES][0], raw2b.ITEMS: [rate_line, rate_line]}
        reversal = {
            raw2b.DOC_DATA: {raw2b.ITC_REVERSAL: [{"b2b": [{**supplier, raw2b.INVOICES: [invoice]}]}]}
        }
        store_raw_return_data(GSTIN, ReturnType.GSTR2B.value, "072020", reversal)
        (section,) = self.adapter.compute_summary("072020")["sections"]

        self.assertEqual((section["documents"], section["taxable_value"], section["igst"]), (1, 2000, 360))

    def test_build_and_store_then_get_summaries_round_trip(self):
        stored = self.adapter.build_and_store_summary(PERIOD_2B)
        self.assertIsNotNone(stored)

        summaries = self.adapter.get_summaries([PERIOD_2B])
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["period"], PERIOD_2B)
        self.assertEqual(summaries[0]["sections"], stored["sections"])

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

    def test_summary_has_no_itc(self):
        summary = self.adapter.compute_summary("032020")
        self.assertTrue(summary["sections"])
        self.assertIsNone(summary["itc_summary"])

    def test_summary_reads_gov_keyed_notes(self):
        """Stored 2A raw keeps the portal's cdn/cdna keys; they must land as CDNR/CDNRA."""
        sections = {s["section"] for s in self.adapter.compute_summary("032020")["sections"]}
        self.assertIn("CDNR", sections)
        self.assertIn("CDNRA", sections)


class TestRawReturnDataRoundTrip(IntegrationTestCase):
    def test_summary_cache_preserves_return_specific_note_signs(self):
        from india_compliance.patches.v17.invalidate_gstr2b_section_summaries import execute

        period = "122024"
        raw_2a = {
            "cdn": [
                {
                    "ctin": GSTIN,
                    "nt": [
                        {
                            "nt_num": "CN1",
                            "ntty": "C",
                            "itms": [{"num": 1, "itm_det": {"txval": 100, "iamt": 18}}],
                        },
                        {
                            "nt_num": "DN1",
                            "ntty": "D",
                            "itms": [{"num": 1, "itm_det": {"txval": 40, "iamt": 7}}],
                        },
                    ],
                }
            ],
            "b2b": [
                {
                    "ctin": GSTIN,
                    "inv": [{"inum": "I1", "itms": [{"num": 1, "itm_det": {"txval": 200, "iamt": 36}}]}],
                }
            ],
        }
        raw_2b = {
            "docdata": {
                "cdnr": [
                    {
                        "ctin": GSTIN,
                        "nt": [
                            {"ntnum": "CN1", "typ": "C", "txval": 100, "igst": 18},
                            {"ntnum": "DN1", "typ": "D", "txval": 40, "igst": 7},
                        ],
                    }
                ],
                "b2b": [{"ctin": GSTIN, "inv": [{"inum": "I1", "txval": 200, "igst": 36}]}],
            },
        }
        old_sections = [
            {
                "section": "B2B",
                "documents": 1,
                "taxable_value": 200,
                "igst": 36,
                "cgst": 0,
                "sgst": 0,
                "cess": 0,
            },
            {
                "section": "CDNR",
                "documents": 2,
                "taxable_value": 140,
                "igst": 25,
                "cgst": 0,
                "sgst": 0,
                "cess": 0,
            },
        ]
        adapters = [(GSTR2AAdapter(GSTIN), raw_2a), (GSTR2BAdapter(GSTIN), raw_2b)]
        for adapter, raw in adapters:
            store_raw_return_data(GSTIN, adapter.return_type, period, raw)
            summary = {"sections": old_sections, "itc_summary": adapter._itc_summary(raw)}
            frappe.db.set_value(
                "GST Return Log",
                adapter._log_name(period),
                "section_summary",
                frappe.as_json(summary),
                update_modified=False,
            )
            self.assertEqual(adapter.get_summaries([period])[0]["sections"], old_sections)

        execute()
        execute()
        for adapter, raw in adapters:
            with self.subTest(return_type=adapter.return_type):
                expected = [dict(section) for section in old_sections]
                if isinstance(adapter, GSTR2BAdapter):
                    expected[1].update(taxable_value=-60, igst=-11)
                self.assertEqual(adapter.get_summaries([period])[0]["sections"], expected)
                self.assertEqual(adapter.compute_summary(period)["sections"], expected)
                frappe.db.set_value(
                    "GST Return Log",
                    adapter._log_name(period),
                    "section_summary",
                    None,
                    update_modified=False,
                )
                self.assertEqual(adapter.get_summaries([period])[0]["sections"], expected)
                self.assertEqual(adapter.get_summaries([period])[0]["sections"], expected)
                self.assertEqual(get_raw_return_data(GSTIN, adapter.return_type, period), raw)

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

    def test_tool_sync_stores_the_summary(self):
        """The tool's sync builds the summary right after the download; nothing waits for a read."""
        period = "102024"
        raw = {"docdata": {"b2b": [{"ctin": GSTIN, "trdnm": "X", "inv": [{"inum": "I1"}, {"inum": "I2"}]}]}}
        store_raw_return_data(GSTIN, ReturnType.GSTR2B.value, period, raw)  # what the download leaves behind
        with patch.object(GSTR2BAdapter, "download"):
            controller._sync_return_data(GSTIN, ReturnType.GSTR2B.value, [period])

        log_name = f"{ReturnType.GSTR2B.value}-{period}-{GSTIN}"
        summary = frappe.parse_json(frappe.db.get_value("GST Return Log", log_name, "section_summary"))
        self.assertEqual(summary["sections"][0]["documents"], 2)

    def test_patch_invalidates_old_2b_summary_and_lazy_read_recomputes_signed_cdnr(self):
        from india_compliance.patches.v17.invalidate_gstr2b_section_summaries import execute

        period_2b = "112024"
        period_2a = "112024"
        raw_2b = {
            "docdata": {
                "cdnr": [
                    {
                        "ctin": GSTIN,
                        "nt": [
                            {"ntnum": "CN1", "typ": "C", "txval": 100, "igst": 18},
                            {"ntnum": "DN1", "typ": "D", "txval": 40, "igst": 7},
                        ],
                    }
                ]
            }
        }
        store_raw_return_data(GSTIN, ReturnType.GSTR2B.value, period_2b, raw_2b)
        store_raw_return_data(GSTIN, ReturnType.GSTR2A.value, period_2a, {"cdn": []})

        log_2b = f"{ReturnType.GSTR2B.value}-{period_2b}-{GSTIN}"
        log_2a = f"{ReturnType.GSTR2A.value}-{period_2a}-{GSTIN}"
        stale_summary = {
            "sections": [
                {
                    "section": "CDNR",
                    "documents": 2,
                    "taxable_value": 140.0,
                    "igst": 25.0,
                    "cgst": 0.0,
                    "sgst": 0.0,
                    "cess": 0.0,
                }
            ],
            "itc_summary": None,
        }
        section_summary_2a = '{"sections":[{"section":"CDNR","taxable_value":123}]}'
        frappe.db.set_value(
            "GST Return Log", log_2b, "section_summary", frappe.as_json(stale_summary), update_modified=False
        )
        frappe.db.set_value(
            "GST Return Log", log_2a, "section_summary", section_summary_2a, update_modified=False
        )
        modified_2b = frappe.db.get_value("GST Return Log", log_2b, "modified")
        modified_2a = frappe.db.get_value("GST Return Log", log_2a, "modified")

        execute()
        execute()

        self.assertFalse(frappe.db.get_value("GST Return Log", log_2b, "section_summary"))
        self.assertEqual(frappe.db.get_value("GST Return Log", log_2a, "section_summary"), section_summary_2a)
        self.assertEqual(frappe.db.get_value("GST Return Log", log_2b, "modified"), modified_2b)
        self.assertEqual(frappe.db.get_value("GST Return Log", log_2a, "modified"), modified_2a)
        self.assertEqual(get_raw_return_data(GSTIN, ReturnType.GSTR2B.value, period_2b), raw_2b)

        summary = GSTR2BAdapter(GSTIN).get_summaries([period_2b])[0]
        cdnr = summary["sections"][0]
        self.assertEqual((cdnr["documents"], cdnr["taxable_value"], cdnr["igst"]), (2, -60.0, -11.0))
        self.assertEqual(frappe.db.get_value("GST Return Log", log_2b, "modified"), modified_2b)


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
        fake = {"sections": [], "itc_summary": None}
        with patch.object(ReturnAdapter, "get_range_summary", return_value=fake) as summary:
            result = self.doc.get_summary(GSTIN, "GSTR-2B", "2020-08-01", "2020-08-31")

        self.assertEqual(result, fake)
        self.assertTrue(summary.called)

    def test_sync_only_accepts_months_the_portal_can_serve(self):
        """Client months land in log names; junk and months past the cut-off are dropped."""
        today = "india_compliance.gst_india.doctype.purchase_reconciliation_tool.getdate"
        with patch(today, return_value=getdate("2021-05-20")):
            result = self.doc.sync_return_data(
                GSTIN, "GSTR-2B", ["../etc", "132021", "", "072021"], "2021-03-01", "2021-08-01"
            )

        self.assertEqual(result["indicator"], "orange")

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
            controller.export_file(GSTIN, "GSTR-2B", "2019-01-01", "2019-12-31")

    def _export_job_id(self, return_type, from_date, to_date, group_by="all"):
        with patch.object(controller.frappe, "enqueue") as enqueue:
            controller.export_file(GSTIN, return_type, from_date, to_date, group_by)
        return enqueue.call_args.kwargs["job_id"]

    def test_export_jobs_are_keyed_on_the_months_and_the_return(self):
        """Dedupe must collapse the same request, and never two different ones."""
        august_2b = self._export_job_id("GSTR-2B", "2020-08-01", "2020-08-31")

        self.assertEqual(self._export_job_id("GSTR-2B", "2020-08-10", "2020-08-20"), august_2b)
        self.assertNotEqual(self._export_job_id("GSTR-2A", "2020-08-01", "2020-08-31"), august_2b)
        self.assertNotEqual(self._export_job_id("GSTR-2B", "2020-09-01", "2020-09-30"), august_2b)

        # one workbook is one workbook, however the grouping was asked for
        quarter = self._export_job_id("GSTR-2B", "2020-07-01", "2020-09-30", "quarterly")
        self.assertEqual(quarter, self._export_job_id("GSTR-2B", "2020-07-01", "2020-09-30", "all"))
        self.assertNotEqual(quarter, self._export_job_id("GSTR-2B", "2020-07-01", "2020-09-30", "monthly"))

    def test_second_requester_is_told_a_build_is_running(self):
        with patch.object(controller.frappe, "enqueue", return_value=None):
            result = controller.export_file(GSTIN, "GSTR-2B", "2020-08-01", "2020-08-31")
        self.assertEqual(result["indicator"], "orange")

    def test_sync_reports_nothing_to_sync(self):
        with patch(
            "india_compliance.gst_india.doctype.purchase_reconciliation_tool"
            ".purchase_reconciliation_tool.get_periods_to_download",
            return_value=[],
        ):
            result = self.doc.sync_return_data(GSTIN, "GSTR-2B", ["082020"], "2020-08-01", "2020-08-31")
        self.assertEqual(result["indicator"], "orange")
