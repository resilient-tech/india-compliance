# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import datetime
import re
from collections import defaultdict
from collections.abc import Sequence
from typing import Literal

import frappe
from frappe import _
from frappe.model.document import bulk_insert
from frappe.query_builder.functions import IfNull
from frappe.utils import (
    add_months,
    get_first_day,
    get_last_day,
    get_table_name,
    getdate,
    random_string,
)

from india_compliance.gst_india.overrides.transaction import validate_mandatory_fields
from india_compliance.gst_india.utils import get_period

SUPPORTED_DOCTYPES = frozenset(("Purchase Invoice", "Bill of Entry"))
SUPPORTED_TABLE_NAMES = frozenset(get_table_name(dt) for dt in SUPPORTED_DOCTYPES)
ITC_CLAIM_PERIOD_DEFERRED = "Deferred"
FILING_STATUS = {
    "Filed": "Filed",  # ACTION : STATUS
    "Not Filed": "Unfiled",
}


def set_or_validate_itc_claim_period(doc) -> None:
    """Set ITC claim period if empty, otherwise validate it."""

    if not doc.get("itc_claim_period"):
        doc.itc_claim_period = _calculate_itc_claim_period(doc)
    else:
        validate_itc_claim_period(doc)


def set_itc_claim_period_on_match(
    doc_names: list[str],
    inward_supply_map: dict[str, str],
    doctype: str = "Purchase Invoice",
) -> None:
    if not doc_names or not inward_supply_map or doctype not in SUPPORTED_DOCTYPES:
        return

    doc_data = _fetch_document_data(doctype, doc_names)
    gstins = {d.company_gstin for d in doc_data if d.company_gstin}
    filed_map = {gstin: _get_filed_periods(gstin) for gstin in gstins}

    inward_data = _fetch_inward_supply_data(list(inward_supply_map.keys()))
    doc_map = {d.name: d for d in doc_data}
    inward_map = {i.name: i for i in inward_data}

    updates = defaultdict(set)
    for inward_name, doc_name in inward_supply_map.items():
        doc = doc_map.get(doc_name)
        if not doc:
            continue

        filed = filed_map.get(doc.company_gstin, set())
        period = _calculate_itc_claim_period(doc, inward_map.get(inward_name), filed)
        if period:
            updates[period].add(doc_name)

    _bulk_update(updates, doctype, "Reconciliation")


def set_itc_claim_period_on_ims_action(
    invoice_names: Sequence[str],
    action: str,
    ims_period: str | None = None,
) -> None:
    if not invoice_names:
        return

    if action not in ("Accepted", "Rejected", "Pending"):
        return

    linked = _fetch_inward_supply_data(invoice_names, only_linked=True)
    if not linked:
        return

    # Group by doctype
    by_doctype = defaultdict(list)
    for link in linked:
        by_doctype[link.link_doctype].append(link.link_name)

    for doctype, doc_names in by_doctype.items():
        updates = defaultdict(set)
        only_claim_period_set = bool(action in ("Rejected", "Pending"))
        doc_data = _fetch_document_data(doctype, doc_names, only_claim_period_set=only_claim_period_set)
        gstins = {d.company_gstin for d in doc_data if d.company_gstin}
        filed_map = {gstin: _get_filed_periods(gstin) for gstin in gstins}

        for d in doc_data:
            filed = filed_map.get(d.company_gstin, set())
            period = _calculate_itc_claim_period(d, None, filed, action, ims_period)

            if period:
                updates[period].add(d.name)

        _bulk_update(updates, doctype, f"IMS Action ({action})")


# =============================================================================
# PUBLIC API
# =============================================================================


@frappe.whitelist()
def get_itc_period_options(company_gstin: str | None = None, posting_date: str | None = None) -> list[str]:
    if not company_gstin or not posting_date:
        return []

    posting_date = getdate(posting_date)
    today = getdate(frappe.utils.today())

    fy_start = _get_gst_fy_start(posting_date)
    start_date = min(fy_start, get_first_day(add_months(posting_date, -3)))

    deadline_date = period_to_date(_get_section_16_4_deadline(posting_date), "last")
    end_date = min(get_last_day(today), deadline_date)

    filed = _get_filed_periods(company_gstin)

    periods = []
    current = end_date
    while current >= start_date:
        period = format_period(current)
        if period not in filed:
            periods.append(period)
        current = add_months(current, -1)

    periods.insert(0, ITC_CLAIM_PERIOD_DEFERRED)
    return periods


@frappe.whitelist()
def update_gstr3b_filing_status(
    company_gstin: str, month_or_quarter: str, year: int | str, status: str
) -> None:
    frappe.has_permission("GST Return Log", "write", throw=True)
    if status not in FILING_STATUS:
        frappe.throw(
            _("Invalid filing status: {0}. Allowed values are: {1}").format(status, ", ".join(FILING_STATUS))
        )

    period = get_period(month_or_quarter, year)
    filters = {"gstin": company_gstin, "return_period": period, "return_type": "GSTR3B"}
    log_name = frappe.db.get_value("GST Return Log", filters)

    if log_name:
        frappe.db.set_value("GST Return Log", log_name, "filing_status", status)
    else:
        frappe.get_doc({"doctype": "GST Return Log", "filing_status": status, **filters}).insert(
            ignore_permissions=True
        )

    frappe.msgprint(
        _("GSTR-3B for {0} {1} marked as {2}.").format(month_or_quarter, year, FILING_STATUS[status]),
        indicator="green",
    )


# =============================================================================
# Period Utilities
# =============================================================================


def format_period(date: str | datetime.date | datetime.datetime) -> str:
    return getdate(date).strftime("%m%Y")


def apply_period_filter(
    query,
    doc,
    from_date: str | datetime.date | datetime.datetime,
    to_date: str | datetime.date | datetime.datetime,
    filter_by: Literal["ITC Claim Period", "Posting Date"] | None = None,
    return_period: str | None = None,
):
    """
    Apply Date period filter to a query.

    Args:
        query: The query builder query
        doc: The doctype table reference (frappe.qb.DocType)
        from_date: Start date for posting date filter
        to_date: End date for posting date filter
        filter_by: (Optional) "ITC Claim Period" or "Posting Date". Defaults to "Posting Date"
        return_period: (Optional) The return period in MMYYYY format.
                      Auto-calculated from to_date if not provided
    """
    if filter_by == "ITC Claim Period" and doc._table_name in SUPPORTED_TABLE_NAMES:
        if not return_period:
            return_period = format_period(to_date)
        return query.where(IfNull(doc.itc_claim_period, "") == return_period)

    return query.where(doc.posting_date[from_date:to_date])


def period_to_date(period: str, day: Literal["first", "last"] = "first") -> datetime.date:
    if not period or len(period) != 6:
        frappe.throw(_("Invalid period format: {0}. Expected MMYYYY.").format(period))

    month, year = int(period[:2]), int(period[2:])
    date = getdate(f"{year}-{month:02d}-01")
    return get_last_day(date) if day == "last" else date


def period_sort_key(period: str) -> str:
    """Convert MMYYYY → YYYYMM for natural string comparison."""
    return period[2:] + period[:2]


def compare_periods(p1: str, p2: str) -> int:
    """Compare two MMYYYY periods. Returns -1, 0, or 1."""
    key1, key2 = period_sort_key(p1), period_sort_key(p2)
    return (key1 > key2) - (key1 < key2)


def _next_period(period: str) -> str:
    return format_period(add_months(period_to_date(period), 1))


def _max_period(p1: str, p2: str) -> str:
    return max(p1, p2, key=period_sort_key)


def _validate_period_format(period: str) -> None:
    if period == ITC_CLAIM_PERIOD_DEFERRED:
        return

    if period and not re.match(r"^(0[1-9]|1[0-2])\d{4}$", period):
        frappe.throw(_("ITC Claim Period '{0}' must be in MMYYYY format").format(period))


# =============================================================================
# GST Fiscal Year
# =============================================================================


def _get_gst_fy_start(date: str | datetime.date | datetime.datetime) -> datetime.date:
    date = getdate(date)
    year = date.year if date.month >= 4 else date.year - 1
    return getdate(f"{year}-04-01")


def _get_section_16_4_deadline(
    posting_date: str | datetime.date | datetime.datetime,
) -> str:
    date = getdate(posting_date)
    year = date.year + 1 if date.month >= 4 else date.year
    return f"11{year}"


# =============================================================================
# Filing Status
# =============================================================================


def _is_gstr3b_filed(gstin: str, period: str | None) -> bool:
    if period == ITC_CLAIM_PERIOD_DEFERRED or not period:
        return False

    filters = {"gstin": gstin, "return_period": period, "return_type": "GSTR3B"}

    return frappe.db.get_value("GST Return Log", filters, "filing_status") == "Filed"


def _get_filed_periods(gstin: str) -> set[str]:
    return set(
        frappe.get_all(
            "GST Return Log",
            filters={"gstin": gstin, "return_type": "GSTR3B", "filing_status": "Filed"},
            pluck="return_period",
        )
    )


def _get_next_unfiled_period(
    gstin: str,
    start_period: str,
    posting_date: str | datetime.date | datetime.datetime,
    filed: set[str] | None = None,
) -> str | None:
    deadline = _get_section_16_4_deadline(posting_date)
    is_filed = (lambda p: p in filed) if filed else (lambda p: _is_gstr3b_filed(gstin, p))

    current = start_period
    while compare_periods(current, deadline) <= 0:
        if not is_filed(current):
            return current
        current = _next_period(current)
    return None


# =============================================================================
# ITC Calculation
# =============================================================================


def _calculate_itc_claim_period(
    doc,
    inward_supply: dict | None = None,
    filed: set[str] | None = None,
    ims_action: str | None = None,
    ims_period: str | None = None,
) -> str | None:
    # skip if already filed
    if filed and doc.itc_claim_period and doc.itc_claim_period in filed:
        return None

    # FIRST PREFERENCE: IMS ACTION

    if ims_action in ("Rejected", "Pending"):
        return ITC_CLAIM_PERIOD_DEFERRED  # defer to next period

    if ims_action == "Accepted" and ims_period:
        return ims_period

    # NEXT PREFERENCE: MATCH FOUND

    if inward_supply and inward_supply.get("ims_action") in ("Rejected", "Pending"):
        return ITC_CLAIM_PERIOD_DEFERRED  # defer to next period

    # default
    posting_period = format_period(doc.posting_date)
    default_period = posting_period

    if inward_supply and inward_supply.get("return_period_2b"):
        default_period = _max_period(posting_period, inward_supply.return_period_2b)

    if doc.get("gst_category") == "Unregistered" and doc.get("is_reverse_charge"):
        return posting_period

    return _get_next_unfiled_period(doc.company_gstin, default_period, doc.posting_date, filed)


def validate_itc_claim_period(doc) -> None:
    validate_mandatory_fields(doc, "itc_claim_period")
    _validate_period_format(doc.itc_claim_period)
    _validate_itc_claim_period_for_rcm_invoice(doc)
    _validate_itc_claim_period_as_per_filing(doc)


def _validate_itc_claim_period_as_per_filing(doc) -> None:
    previous = doc.get_doc_before_save()
    if not previous:
        return

    if previous.itc_claim_period != doc.itc_claim_period:
        filed_period = None
        if _is_gstr3b_filed(doc.company_gstin, previous.itc_claim_period):
            filed_period = previous.itc_claim_period
        if _is_gstr3b_filed(doc.company_gstin, doc.itc_claim_period):
            filed_period = doc.itc_claim_period

        if not filed_period:
            return

        frappe.throw(
            _("Cannot change ITC Claim Period from {0} to {1}. GSTR-3B already filed for {2}.").format(
                previous.itc_claim_period, doc.itc_claim_period, filed_period
            )
        )


def _validate_itc_claim_period_for_rcm_invoice(doc) -> None:
    """For Unregistered RCM, ITC must be claimed in the same period as posting."""
    if (
        doc.doctype == "Purchase Invoice"
        and doc.gst_category == "Unregistered"
        and doc.is_reverse_charge
        and doc.itc_claim_period != format_period(doc.posting_date)
    ):
        frappe.throw(
            _(
                "ITC Claim Period must be {0} (same as posting date) for purchases from"
                " Unregistered suppliers under Reverse Charge."
            ).format(format_period(doc.posting_date))
        )


# =============================================================================
# Bulk Processing
# =============================================================================


def _bulk_update(updates: dict[str, set[str]], doctype: str, source: str) -> None:
    """Bulk update with audit trail."""
    if not updates:
        return

    for period, names in updates.items():
        frappe.db.set_value(
            doctype,
            {"name": ["in", names]},
            "itc_claim_period",
            period,
            update_modified=True,
        )

    user = frappe.session.user
    current_time = frappe.utils.now()
    comments = []
    for period, names in updates.items():
        content = _("ITC Claim Period set to {0} via {1}").format(period, source)
        for name in names:
            comment = frappe.new_doc("Comment")
            comment.update(
                {
                    "name": random_string(10),
                    "comment_type": "Info",
                    "comment_email": user,
                    "comment_by": user,
                    "creation": current_time,
                    "modified": current_time,
                    "modified_by": user,
                    "owner": user,
                    "reference_doctype": doctype,
                    "reference_name": name,
                    "content": content,
                }
            )
            comments.append(comment)

    if comments:
        bulk_insert("Comment", comments, ignore_duplicates=True)


def _fetch_document_data(doctype: str, names: list[str], only_claim_period_set: bool = False) -> list[dict]:
    doc = frappe.qb.DocType(doctype)
    query = (
        frappe.qb.from_(doc)
        .select(
            doc.name,
            doc.posting_date,
            doc.company_gstin,
            doc.itc_claim_period,
        )
        .where(doc.name.isin(names))
    )

    if doctype == "Purchase Invoice":
        query = query.select(doc.gst_category, doc.is_reverse_charge)

    if only_claim_period_set:
        query = query.where(doc.itc_claim_period.isnotnull())
        query = query.where(doc.itc_claim_period != ITC_CLAIM_PERIOD_DEFERRED)
        query = query.where(doc.itc_claim_period != "")

    return query.run(as_dict=True)


def _fetch_inward_supply_data(names: Sequence[str], only_linked: bool = False) -> list[dict]:
    gstr2 = frappe.qb.DocType("GST Inward Supply")
    query = (
        frappe.qb.from_(gstr2)
        .select(
            gstr2.name,
            gstr2.return_period_2b,
            gstr2.ims_action,
            gstr2.link_name,
            gstr2.link_doctype,
        )
        .where(gstr2.name.isin(names))
    )

    if only_linked:
        query = query.where(gstr2.link_name.isnotnull())
        query = query.where(gstr2.link_name != "")
        query = query.where(gstr2.link_doctype.isin(SUPPORTED_DOCTYPES))

    return query.run(as_dict=True)
