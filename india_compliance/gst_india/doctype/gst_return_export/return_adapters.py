# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""One adapter per return type: download, where the sections sit in the raw data, summary."""

from typing import ClassVar

import frappe
from frappe.utils import flt

from india_compliance.gst_india.doctype.gst_return_export.template_exporter import as_section_dict
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
ITC_REVERSAL_SECTION = "ITC Reversal"
TAX_FIELDS = ("igst", "cgst", "sgst", "cess")
SECTION_FIELDS = ("documents", "taxable_value", *TAX_FIELDS)
SUPPLY_PARTS = (raw2b.NON_REVERSE_CHARGE_SUPPLIES, raw2b.ISD_SUPPLIES, raw2b.REVERSE_CHARGE_SUPPLIES)
ITC_CARDS = {
    "available": (
        (1, raw2b.ITC_AVAILABLE, (*SUPPLY_PARTS, raw2b.IMPORTS)),
        (-1, raw2b.ITC_AVAILABLE, (raw2b.CREDIT_NOTES,)),
        (-1, raw2b.ITC_NOT_AVAILABLE, (raw2b.CREDIT_NOTES,)),
    ),
    "not_available": ((1, raw2b.ITC_NOT_AVAILABLE, SUPPLY_PARTS),),
    "reversal": ((1, raw2b.ITC_REVERSAL, (raw2b.NON_REVERSE_CHARGE_SUPPLIES,)),),
}

RETURN_TYPE_MAP = {"GSTR-2A": ReturnType.GSTR2A.value, "GSTR-2B": ReturnType.GSTR2B.value}


def normalize_return_type(return_type):
    """UI label / enum value -> enum value."""
    return RETURN_TYPE_MAP.get(return_type, return_type)


def section_rank(section):
    return SECTION_ORDER.index(section) if section in SECTION_ORDER else len(SECTION_ORDER)


def section_totals(section, rows):
    return {
        "section": section,
        "documents": len(rows),
        "taxable_value": flt(sum(flt(row.get("taxable_value")) for row in rows)),
        **{t: flt(sum(flt(row.get(t)) for row in rows)) for t in TAX_FIELDS},
    }


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
        itc_months = [s["itc_summary"] for s in stored.values() if s.get("itc_summary")]
        itc = (
            {card: sum(flt(month[card]) for month in itc_months) for card in ITC_CARDS}
            if itc_months
            else None
        )
        return {
            "sections": sorted(sections.values(), key=lambda s: section_rank(s["section"])),
            "itc_summary": itc,
        }

    def get_summaries(self, periods):
        """Cached month summaries; built here when the sync predates the cache. No raw, no summary."""
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
        for category in self.handler_class.SECTIONS:
            groups = docdata.get(category.lower())
            if not groups:
                continue

            rows = self.get_handler(period, category).get_all_transactions(groups)
            sections.append(section_totals(category, rows))

        sections.extend(self.extra_sections(period, docdata))
        sections.sort(key=lambda s: section_rank(s["section"]))
        return {"sections": sections, "itc_summary": self._itc_summary(raw)}

    @staticmethod
    def raw_sections(raw):
        """Where the section lists sit (2A: top level, 2B: docdata)."""
        return raw or {}

    def get_handler(self, period, category):
        """The sync's reader for one category."""
        return self.handler_class(None, self.gstin, period, category)

    def extra_sections(self, period, docdata):
        return []

    def _itc_summary(self, raw):
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

    def extra_sections(self, period, docdata):
        reversal = as_section_dict(docdata.get(raw2b.ITC_REVERSAL))
        rows = [
            row
            for category, groups in reversal.items()
            if category.upper() in self.handler_class.SECTIONS
            for row in self.get_handler(period, category.upper()).get_all_transactions(groups)
        ]
        return [section_totals(ITC_REVERSAL_SECTION, rows)] if rows else []

    def _itc_summary(self, raw):
        itcsumm = (raw or {}).get(raw2b.ITC_SUMMARY) or {}

        def tax(block, part):
            return sum(flt(((itcsumm.get(block) or {}).get(part) or {}).get(t)) for t in TAX_FIELDS)

        return {
            card: flt(sum(sign * tax(block, part) for sign, block, parts in terms for part in parts), 2)
            for card, terms in ITC_CARDS.items()
        }
