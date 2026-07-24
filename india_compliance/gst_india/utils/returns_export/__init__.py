# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""
Ports-and-adapters layer for the GST Return Export tool.

`ReturnAdapter` is the port; one adapter per return type supplies download, summary
aggregation and ITC. Raw payload (`filed`) and prepared summary (`summary`) both live
on the period's GST Return Log row.
"""

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Count, Sum
from frappe.utils import cint, flt, now

from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    DOCTYPE as RETURN_LOG,
)
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    get_gst_return_log,
)
from india_compliance.gst_india.utils.gstr_utils import ReturnType

SECTION_ORDER = ["B2B", "B2BA", "CDNR", "CDNRA", "ISD", "ISDA", "IMPG", "IMPGSEZ"]
TAX_FIELDS = ("igst", "cgst", "sgst", "cess")
SECTION_FIELDS = ("documents", "taxable_value", *TAX_FIELDS)

RETURN_TYPE_MAP = {"GSTR-2A": ReturnType.GSTR2A.value, "GSTR-2B": ReturnType.GSTR2B.value}


def normalize_return_type(return_type):
    """Accept the UI label ('GSTR-2B'), the enum value ('GSTR2b'), or the ReturnType member."""
    if isinstance(return_type, ReturnType):
        return return_type.value
    return RETURN_TYPE_MAP.get(return_type, return_type)


def merge_raw(existing, new):
    """Deep-merge raw payload chunks: dicts recurse, lists concat, numbers add, else
    newer wins (but a null in `new` never clobbers accumulated data)."""
    if isinstance(existing, dict) and isinstance(new, dict):
        merged = dict(existing)
        for key, value in new.items():
            merged[key] = merge_raw(merged[key], value) if key in merged else value
        return merged

    if isinstance(existing, list) and isinstance(new, list):
        return existing + new

    if isinstance(existing, (int, float)) and isinstance(new, (int, float)):
        return existing + new

    return existing if new is None else new


class ReturnAdapter:
    """Port the tool calls; each return type is an adapter subclass (see ADAPTERS)."""

    return_type = None

    def __init__(self, gstin):
        self.gstin = gstin

    @classmethod
    def for_return(cls, return_type, gstin):
        if adapter := ADAPTERS.get(return_type):
            return adapter(gstin)
        frappe.throw(_("Export is not supported for {0}").format(return_type))

    def build_and_store_summary(self, period):
        """Store the period summary on the log's `summary` field; None if no data."""
        summary = self.compute_summary(period)
        if not summary["sections"]:
            return None

        summary["last_updated_on"] = now()
        get_gst_return_log(self._log_name(period)).db_set("summary", frappe.as_json(summary))
        return summary

    def get_summaries(self, periods):
        """Batch-read the prepared per-period summaries in one query."""
        names = {self._log_name(period): period for period in periods}
        rows = frappe.get_all(RETURN_LOG, filters={"name": ("in", list(names))}, fields=["name", "summary"])
        stored = {names[row.name]: frappe.parse_json(row.summary) for row in rows if row.summary}
        return [{"period": period, **stored[period]} for period in periods if period in stored]

    def get_range_summary(self, periods):
        """Section-first range summary: each section summed across months with a per-month
        breakdown and consolidated ITC. Built from stored monthly summaries. Sync state is
        not reported here; get_sync_status owns that."""
        stored = {s["period"]: s for s in self.get_summaries(periods)}

        sections = {}
        for period in periods:
            summary = stored.get(period)
            if not summary:
                continue
            for section in summary["sections"]:
                row = sections.setdefault(
                    section["section"],
                    {"section": section["section"], "months": [], **{f: 0 for f in SECTION_FIELDS}},
                )
                for field in SECTION_FIELDS:
                    row[field] += flt(section[field])
                row["months"].append({"period": period, **{f: flt(section[f]) for f in SECTION_FIELDS}})

        cumulative = _cumulate(stored.values())
        return {
            "sections": sorted(sections.values(), key=lambda s: _section_rank(s["section"])),
            "totals": cumulative["totals"],
            "itc": cumulative["itc"],
        }

    def get_sync_status(self, periods):
        """Per-month sync state for the sync picker / missing-sync banner.

        A month counts as synced only when its raw payload (the log's `filed` attachment)
        is stored — that's what the export consumes. A period downloaded before this tool
        existed (no stored payload) is reported as not synced, so the banner prompts a
        re-sync instead of the export failing with "no data".

        One query, small columns only: the `filed` filter runs in the DB and `modified`
        doubles as last-synced time, so no summary blob is loaded."""
        names = {self._log_name(period): period for period in periods}
        synced = {
            names[row.name]: row.modified
            for row in frappe.get_all(
                RETURN_LOG,
                filters={"name": ("in", list(names)), "filed": ("is", "set")},
                fields=["name", "modified"],
            )
        }

        return {
            "periods": [
                {
                    "period": period,
                    "synced": period in synced,
                    "last_updated_on": str(synced[period]) if period in synced else None,
                }
                for period in periods
            ],
            "has_missing_sync": any(period not in synced for period in periods),
        }

    def _log_name(self, period):
        return f"{self.return_type}-{period}-{self.gstin}"


class GSTR2Adapter(ReturnAdapter):
    """Common to GSTR-2A/2B: summary aggregated from GST Inward Supply."""

    period_field = None
    downloaded_flag = None

    def _base_query(self, period):
        GIS = frappe.qb.DocType("GST Inward Supply")
        return (
            frappe.qb.from_(GIS)
            .where(GIS.company_gstin == self.gstin)
            .where(GIS[self.downloaded_flag] == 1)
            .where(GIS[self.period_field] == period)
        )

    def compute_summary(self, period):
        GIS = frappe.qb.DocType("GST Inward Supply")
        rows = (
            self._base_query(period)
            .select(
                GIS.classification,
                Count(GIS.name).as_("documents"),
                Sum(GIS.taxable_value).as_("taxable_value"),
                *(Sum(GIS[t]).as_(t) for t in TAX_FIELDS),
                *self._itc_select(GIS),
            )
            .groupby(GIS.classification)
            .run(as_dict=True)
        )

        sections = [
            {
                "section": row.classification,
                "documents": cint(row.documents),
                "taxable_value": flt(row.taxable_value),
                **{t: flt(row[t]) for t in TAX_FIELDS},
            }
            for row in rows
        ]
        sections.sort(key=lambda s: _section_rank(s["section"]))

        totals = {
            "documents": sum(s["documents"] for s in sections),
            "taxable_value": sum(s["taxable_value"] for s in sections),
            **{t: sum(s[t] for s in sections) for t in TAX_FIELDS},
        }
        return {"sections": sections, "totals": totals, "itc": self._itc(rows)}

    def _itc_select(self, GIS):
        return []

    def _itc(self, rows):
        return None


class GSTR2AAdapter(GSTR2Adapter):
    return_type = ReturnType.GSTR2A.value
    period_field = "sup_return_period"
    downloaded_flag = "is_downloaded_from_2a"

    def download(self, periods):
        from india_compliance.gst_india.utils.gstr_2 import download_gstr_2a

        download_gstr_2a(self.gstin, periods)


class GSTR2BAdapter(GSTR2Adapter):
    return_type = ReturnType.GSTR2B.value
    period_field = "return_period_2b"
    downloaded_flag = "is_downloaded_from_2b"

    def download(self, periods):
        from india_compliance.gst_india.utils.gstr_2 import download_gstr_2b

        download_gstr_2b(self.gstin, periods)

    def _itc_select(self, GIS):
        total_tax = GIS.igst + GIS.cgst + GIS.sgst + GIS.cess
        available = GIS.itc_availability == "Yes"
        reversal = GIS.itc_availability == "Temporary"
        return [
            Sum(Case().when(available, total_tax).else_(0)).as_("itc_available"),
            Sum(Case().when(reversal, total_tax).else_(0)).as_("itc_reversal"),
            Sum(Case().when(available | reversal, 0).else_(total_tax)).as_("itc_not_available"),
        ]

    def _itc(self, rows):
        return {
            "available": sum(flt(r.itc_available) for r in rows),
            "not_available": sum(flt(r.itc_not_available) for r in rows),
            "reversal": sum(flt(r.itc_reversal) for r in rows),
        }


ADAPTERS = {
    GSTR2AAdapter.return_type: GSTR2AAdapter,
    GSTR2BAdapter.return_type: GSTR2BAdapter,
}


def _cumulate(summaries):
    """Consolidated headline for the range: sum per-period totals and ITC."""
    summaries = list(summaries)
    totals = {k: 0 for k in ("documents", "taxable_value", *TAX_FIELDS)}
    for summary in summaries:
        for key in totals:
            totals[key] += flt(summary["totals"][key])

    itc_parts = [s["itc"] for s in summaries if s.get("itc")]
    itc = None
    if itc_parts:
        itc = {
            bucket: sum(flt(part[bucket]) for part in itc_parts)
            for bucket in ("available", "not_available", "reversal")
        }
    return {"totals": totals, "itc": itc}


def _section_rank(section):
    return SECTION_ORDER.index(section) if section in SECTION_ORDER else len(SECTION_ORDER)
