# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""
Prepared per-period summary for the GST Return Export tool (M4).

The summary is computed ONCE per period right after a successful sync and stored
here (inline JSON), so the view reads a prepared summary instead of re-aggregating
on every open. Recomputed only when the period is re-synced (`last_updated_on`).
One row per (gstin, return_type, return_period); shared across users.

Source: `GST Inward Supply` — the normalized rows our own Sync creates (via
create_transactions). We aggregate those; the raw payload stays for the export.
2B is filtered by `return_period_2b`, 2A by `sup_return_period`, each guarded by
the `is_downloaded_from_2a/2b` flag the save path sets.
"""

import frappe
from frappe.model.document import Document
from frappe.query_builder import Case
from frappe.query_builder.functions import Count, Sum
from frappe.utils import cint, flt, now

from india_compliance.gst_india.utils.gstr_utils import ReturnType

# Canonical display order of sections.
SECTION_ORDER = ["B2B", "B2BA", "CDNR", "CDNRA", "ISD", "ISDA", "IMPG", "IMPGSEZ"]
TAX_FIELDS = ("igst", "cgst", "sgst", "cess")


class GSTReturnSummary(Document):
    pass


def build_and_store_summary(gstin, return_type, return_period):
    """Compute the period's summary from GST Inward Supply and store it. Returns
    the summary, or None if the period has no data yet (e.g. still queued)."""
    summary = compute_return_summary(gstin, return_type, return_period)
    if not summary["sections"]:
        return None

    set_return_summary(gstin, return_type, return_period, summary)
    return summary


def compute_return_summary(gstin, return_type, return_period):
    """Aggregate GST Inward Supply into a section-wise (+ ITC, for 2B) summary."""
    GIS = frappe.qb.DocType("GST Inward Supply")
    is_2b = return_type == ReturnType.GSTR2B.value

    def base_query():
        query = frappe.qb.from_(GIS).where(GIS.company_gstin == gstin)
        if is_2b:
            return query.where(GIS.is_downloaded_from_2b == 1).where(GIS.return_period_2b == return_period)
        return query.where(GIS.is_downloaded_from_2a == 1).where(GIS.sup_return_period == return_period)

    select = [
        GIS.classification,
        Count(GIS.name).as_("documents"),
        Count(GIS.supplier_gstin).distinct().as_("suppliers"),
        Sum(GIS.taxable_value).as_("taxable_value"),
        *(Sum(GIS[t]).as_(t) for t in TAX_FIELDS),
    ]
    if is_2b:
        is_available = GIS.itc_availability == "Yes"
        is_reversal = GIS.itc_availability == "Temporary"
        select += [Sum(Case().when(is_available, GIS[t]).else_(0)).as_(f"avl_{t}") for t in TAX_FIELDS]
        select += [Sum(Case().when(is_reversal, GIS[t]).else_(0)).as_(f"rev_{t}") for t in TAX_FIELDS]
        select += [
            Sum(Case().when(is_available | is_reversal, 0).else_(GIS[t])).as_(f"nav_{t}") for t in TAX_FIELDS
        ]

    section_rows = base_query().select(*select).groupby(GIS.classification).run(as_dict=True)

    sections = []
    totals = {k: 0 for k in ("documents", "taxable_value", *TAX_FIELDS)}
    itc_available = {t: 0 for t in TAX_FIELDS}
    itc_not_available = {t: 0 for t in TAX_FIELDS}
    itc_reversal = {t: 0 for t in TAX_FIELDS}
    for row in section_rows:
        section = {
            "section": row.classification,
            "suppliers": cint(row.suppliers),
            "documents": cint(row.documents),
            "taxable_value": flt(row.taxable_value),
            **{t: flt(row[t]) for t in TAX_FIELDS},
        }
        sections.append(section)
        totals["documents"] += section["documents"]
        totals["taxable_value"] += section["taxable_value"]
        for t in TAX_FIELDS:
            totals[t] += section[t]
            if is_2b:
                itc_available[t] += flt(row[f"avl_{t}"])
                itc_not_available[t] += flt(row[f"nav_{t}"])
                itc_reversal[t] += flt(row[f"rev_{t}"])

    sections.sort(key=lambda s: _section_rank(s["section"]))

    totals["suppliers"] = cint(base_query().select(Count(GIS.supplier_gstin).distinct()).run()[0][0])

    itc = _build_itc(itc_available, itc_not_available, itc_reversal) if is_2b else None
    return {"sections": sections, "totals": totals, "itc": itc}


def _section_rank(section):
    return SECTION_ORDER.index(section) if section in SECTION_ORDER else len(SECTION_ORDER)


def _build_itc(available, not_available, reversal):
    """Attach a `total` to each of the three ITC buckets (already summed per tax
    field in the scan) for display."""
    buckets = {"available": available, "not_available": not_available, "reversal": reversal}
    for bucket in buckets.values():
        bucket["total"] = sum(bucket[t] for t in TAX_FIELDS)
    return buckets


def set_return_summary(gstin, return_type, return_period, summary):
    """Upsert the stored summary for one (gstin, return_type, period)."""
    fields = {"gstin": gstin, "return_type": return_type, "return_period": return_period}
    payload = {"summary": frappe.as_json(summary), "last_updated_on": now()}

    if name := frappe.db.get_value("GST Return Summary", fields):
        frappe.db.set_value("GST Return Summary", name, payload)
    else:
        frappe.get_doc({"doctype": "GST Return Summary", **fields, **payload}).insert(ignore_permissions=True)


def get_return_summary(gstin, return_type, return_period):
    """Read the stored summary (parsed) for one period, or None."""
    row = frappe.db.get_value(
        "GST Return Summary",
        {"gstin": gstin, "return_type": return_type, "return_period": return_period},
        ["summary", "last_updated_on"],
        as_dict=True,
    )
    if not row or not row.summary:
        return None

    data = frappe.parse_json(row.summary)
    data["last_updated_on"] = row.last_updated_on
    return data
