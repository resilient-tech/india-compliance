# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""One adapter per return type: download, where the sections sit in the raw data, summary."""

from typing import ClassVar

import frappe
from frappe.utils import cint, flt

from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    DOCTYPE as RETURN_LOG,
)
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    get_raw_return_data,
)
from india_compliance.gst_india.utils.gstr_2 import download_gstr_2a, download_gstr_2b
from india_compliance.gst_india.utils.gstr_2.gstr import GSTR
from india_compliance.gst_india.utils.gstr_2.gstr_2a import GSTR2a
from india_compliance.gst_india.utils.gstr_2.gstr_2b import GSTR2b
from india_compliance.gst_india.utils.gstr_utils import ReturnType
from india_compliance.gst_returns.fields.gstr2 import RawField2b as raw2b

SECTION_ORDER = [
    "B2B",
    "B2BA",
    "CDNR",
    "CDNRA",
    "ISD",
    "ISDA",
    "ECOM",
    "ECOMA",
    "IMPG",
    "IMPGSEZ",
    "TDS",
    "TCS",
]
TAX_FIELDS = ("igst", "cgst", "sgst", "cess")
SECTION_FIELDS = ("documents", "taxable_value", *TAX_FIELDS)
ITC_BUCKETS = ("available", "not_available", "reversal")

RETURN_TYPE_MAP = {"GSTR-2A": ReturnType.GSTR2A.value, "GSTR-2B": ReturnType.GSTR2B.value}


def normalize_return_type(return_type):
    """UI label / enum value -> enum value."""
    return RETURN_TYPE_MAP.get(return_type, return_type)


def section_rank(section):
    return SECTION_ORDER.index(section) if section in SECTION_ORDER else len(SECTION_ORDER)


def sum_summaries(summaries):
    """Totals and ITC added across month summaries. ITC None when no month has it."""
    summaries = list(summaries)
    totals = {k: 0 for k in SECTION_FIELDS}
    for summary in summaries:
        for key in totals:
            totals[key] += flt(summary["totals"][key])

    itc_parts = [s["itc"] for s in summaries if s.get("itc")]
    itc = None
    if itc_parts:
        itc = {bucket: sum(flt(part[bucket]) for part in itc_parts) for bucket in ITC_BUCKETS}
    return {"totals": totals, "itc": itc}


class ReturnAdapter:
    """Data access for one return type. Registered via its exporter."""

    return_type: ClassVar[str]
    handler_class: ClassVar[type[GSTR]]
    first_month: ClassVar[str]

    def __init__(self, gstin):
        self.gstin = gstin

    # ---- summary, read path: range -> months -> one month

    def get_range_summary(self, periods):
        """Sections summed across the months, with per-month breakdown and overall ITC."""
        stored = {s["period"]: s for s in self.get_summaries(periods)}

        # add up per section
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

        # overall
        cumulative = sum_summaries(stored.values())
        return {
            "sections": sorted(sections.values(), key=lambda s: section_rank(s["section"])),
            "totals": cumulative["totals"],
            "itc": cumulative["itc"],
        }

    def get_summaries(self, periods):
        """Cached month summaries, built on first read. No raw, no summary."""
        names = {self._log_name(period): period for period in periods}
        logs = frappe.get_all(
            RETURN_LOG,
            filters={"name": ("in", list(names)), "raw_gov_data": ("is", "set")},
            fields=["name", "section_summary"],
            limit=len(names),
        )

        # cached, else build now
        stored = {}
        for log in logs:
            period = names[log.name]
            summary = (
                frappe.parse_json(log.section_summary)
                if log.section_summary
                else self.build_and_store_summary(period)
            )
            if summary:
                stored[period] = summary

        return [{"period": period, **stored[period]} for period in periods if period in stored]

    def build_and_store_summary(self, period):
        """Cache the month's summary on the log. None if no data."""
        summary = self.compute_summary(period)
        if not summary["sections"]:
            return None

        # a cache, not an edit: `modified` stay the month's sync time
        frappe.db.set_value(
            RETURN_LOG,
            self._log_name(period),
            "section_summary",
            frappe.as_json(summary),
            update_modified=False,
        )
        return summary

    def compute_summary(self, period):
        """Per-section counts and tax totals for one period, from stored raw."""
        raw = get_raw_return_data(self.gstin, self.return_type, period)
        docdata = self.raw_sections(raw)

        # per section
        sections = []
        itc_rows = []
        for category in self.handler_class.SECTIONS:
            groups = docdata.get(category.lower())
            if not groups:
                continue

            rows = self.get_handler(period, category).get_all_transactions(groups)
            sections.append(
                {
                    "section": category,
                    "documents": len(rows),
                    "taxable_value": flt(sum(flt(row.get("taxable_value")) for row in rows)),
                    **{t: flt(sum(flt(row.get(t)) for row in rows)) for t in TAX_FIELDS},
                }
            )
            itc_rows.extend(rows)

        # totals
        sections.sort(key=lambda s: section_rank(s["section"]))
        totals = {
            field: cint(sum(s[field] for s in sections))
            if field == "documents"
            else flt(sum(s[field] for s in sections))
            for field in SECTION_FIELDS
        }
        return {"sections": sections, "totals": totals, "itc": self._itc(itc_rows)}

    @staticmethod
    def raw_sections(raw):
        """Where the section lists sit (2A: top level, 2B: docdata)."""
        return raw or {}

    def get_handler(self, period, category):
        """The sync's reader for one category."""
        return self.handler_class(None, self.gstin, period, category)

    def _itc(self, rows):
        return None

    # ---- sync state

    def get_sync_status(self, periods):
        """Per-month sync state. Synced = raw stored."""
        names = {self._log_name(period): period for period in periods}
        synced = {
            names[row.name]: row.modified
            for row in frappe.get_all(
                RETURN_LOG,
                filters={"name": ("in", list(names)), "raw_gov_data": ("is", "set")},
                fields=["name", "modified"],
                limit=len(names),
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


# stored 2A raw keeps the gov section keys; readers use category names
GOV_KEYS_2A = {"cdnr": "cdn", "cdnra": "cdna"}


class GSTR2AAdapter(ReturnAdapter):
    return_type = ReturnType.GSTR2A.value
    handler_class = GSTR2a
    first_month = "2017-07-01"

    def download(self, periods):
        download_gstr_2a(self.gstin, periods)

    @staticmethod
    def raw_sections(raw):
        raw = raw or {}
        return {**raw, **{category: raw[gov] for category, gov in GOV_KEYS_2A.items() if raw.get(gov)}}


class GSTR2BAdapter(ReturnAdapter):
    return_type = ReturnType.GSTR2B.value
    handler_class = GSTR2b
    first_month = "2020-07-01"

    def download(self, periods):
        download_gstr_2b(self.gstin, periods)

    @staticmethod
    def raw_sections(raw):
        return (raw or {}).get(raw2b.DOC_DATA) or {}

    def _itc(self, rows):
        """Total tax split by ITC availability."""
        itc = dict.fromkeys(ITC_BUCKETS, 0)
        buckets = {"Yes": "available", "Temporary": "reversal"}
        for row in rows:
            total_tax = sum(flt(row.get(t)) for t in TAX_FIELDS)
            itc[buckets.get(row.get("itc_availability"), "not_available")] += total_tax
        return itc
