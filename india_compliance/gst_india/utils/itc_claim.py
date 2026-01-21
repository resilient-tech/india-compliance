# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import re
from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import bulk_insert
from frappe.query_builder.functions import IfNull
from frappe.utils import add_months, get_first_day, get_last_day, getdate, random_string

from india_compliance.gst_india.utils import get_period

SUPPORTED_DOCTYPES = ("Purchase Invoice", "Bill of Entry")


# =============================================================================
# PUBLIC API
# =============================================================================


def set_or_validate_itc_claim_period(doc):
    """Set ITC claim period if empty, otherwise validate it."""

    if not doc.get("itc_claim_period"):
        doc.itc_claim_period = _calculate_itc_claim_period(doc)
    else:
        _validate_itc_claim_period(doc)


def set_itc_claim_period_on_match(
    doc_names, inward_supply_map, doctype="Purchase Invoice"
):
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


def set_itc_claim_period_on_ims_action(invoice_names, action, ims_period=None):
    if not invoice_names:
        return

    linked = _fetch_linked_documents(invoice_names)
    if not linked:
        return

    # Group by doctype
    by_doctype = defaultdict(list)
    for l in linked:
        by_doctype[l.link_doctype].append(l.link_name)

    for doctype, doc_names in by_doctype.items():
        updates = defaultdict(set)

        if action == "Accepted":
            doc_data = _fetch_document_data(doctype, doc_names)

        elif action in ("Rejected", "Pending"):
            doc_data = _fetch_document_data(
                doctype, doc_names, only_claim_period_set=True
            )

        gstins = {d.company_gstin for d in doc_data if d.company_gstin}
        filed_map = {gstin: _get_filed_periods(gstin) for gstin in gstins}

        for d in doc_data:
            filed = filed_map.get(d.company_gstin, set())
            period = _calculate_itc_claim_period(d, None, filed, action, ims_period)

            if period is not None:
                updates[period].add(d.name)

        _bulk_update(updates, doctype, f"IMS Action ({action})")


@frappe.whitelist()
def get_itc_period_options(company_gstin=None, posting_date=None):
    if not company_gstin or not posting_date:
        return []

    posting_date = getdate(posting_date)
    today = getdate(frappe.utils.today())

    fy_start = _get_gst_fy_start(posting_date)
    start_date = min(fy_start, get_first_day(add_months(posting_date, -3)))

    deadline_date = _period_to_date(_get_section_16_4_deadline(posting_date), "last")
    end_date = min(get_last_day(today), deadline_date)

    filed = _get_filed_periods(company_gstin)

    periods = []
    current = start_date
    while current <= end_date:
        period = format_period(current)
        if period not in filed:
            periods.append(period)
        current = add_months(current, 1)

    return periods


@frappe.whitelist()
def update_gstr3b_filing_status(company_gstin, month_or_quarter, year, status):
    frappe.has_permission("GST Return Log", "write", throw=True)

    period = get_period(month_or_quarter, year)
    filters = {"gstin": company_gstin, "return_period": period, "return_type": "GSTR3B"}
    log_name = frappe.db.get_value("GST Return Log", filters)

    if log_name:
        frappe.db.set_value("GST Return Log", log_name, "filing_status", status)
    else:
        frappe.get_doc(
            {"doctype": "GST Return Log", "filing_status": status, **filters}
        ).insert(ignore_permissions=True)

    _sync_gstr3b_report_status(company_gstin, month_or_quarter, year, status)

    frappe.msgprint(
        _("GSTR-3B for {0} {1} marked as {2}.").format(
            month_or_quarter, year, _("Filed") if status == "Filed" else _("Unfiled")
        ),
        indicator="green",
    )


# =============================================================================
# Period Utilities
# =============================================================================


def format_period(date):
    return getdate(date).strftime("%m%Y")


def apply_itc_period_filter(query, doc, filter_by, return_period, from_date, to_date):
    """
    Apply ITC period filter to a query.

    Args:
        query: The query builder query
        doc: The doctype table reference (frappe.qb.DocType)
        filter_by: "ITC Claim Period" or "Posting Date"
        return_period: The return period in MMYYYY format
        from_date: Start date for posting date filter
        to_date: End date for posting date filter

    Returns:
        Modified query with the appropriate filter applied
    """
    if filter_by == "ITC Claim Period":
        return query.where(IfNull(doc.itc_claim_period, "") == return_period)

    return query.where(doc.posting_date[from_date:to_date])


def _period_to_date(period, day="first"):
    if not period or len(period) != 6:
        frappe.throw(_("Invalid period format: {0}. Expected MMYYYY.").format(period))

    month, year = int(period[:2]), int(period[2:])
    date = getdate(f"{year}-{month:02d}-01")
    return get_last_day(date) if day == "last" else date


def _compare_periods(p1, p2):
    return (
        -1
        if p1[2:] + p1[:2] < p2[2:] + p2[:2]
        else (1 if p1[2:] + p1[:2] > p2[2:] + p2[:2] else 0)
    )


def _next_period(period):
    return format_period(add_months(_period_to_date(period), 1))


def _max_period(p1, p2):
    return p1 if _compare_periods(p1, p2) >= 0 else p2


def _validate_period_format(period):
    if period and not re.match(r"^(0[1-9]|1[0-2])\d{4}$", period):
        frappe.throw(
            _("ITC Claim Period '{0}' must be in MMYYYY format").format(period)
        )


# =============================================================================
# GST Fiscal Year
# =============================================================================


def _get_gst_fy_start(date):
    date = getdate(date)
    year = date.year if date.month >= 4 else date.year - 1
    return getdate(f"{year}-04-01")


def _get_section_16_4_deadline(posting_date):
    date = getdate(posting_date)
    year = date.year + 1 if date.month >= 4 else date.year
    return f"11{year}"


# =============================================================================
# Filing Status
# =============================================================================


def _is_gstr3b_filed(gstin, period):
    log_name = f"GSTR3B-{period}-{gstin}"
    return frappe.db.get_value("GST Return Log", log_name, "filing_status") == "Filed"


def _get_filed_periods(gstin):
    return set(
        frappe.get_all(
            "GST Return Log",
            filters={"gstin": gstin, "return_type": "GSTR3B", "filing_status": "Filed"},
            pluck="return_period",
        )
    )


def _get_next_unfiled_period(gstin, start_period, posting_date, filed=None):
    deadline = _get_section_16_4_deadline(posting_date)
    is_filed = (
        (lambda p: p in filed) if filed else (lambda p: _is_gstr3b_filed(gstin, p))
    )

    current = start_period
    while _compare_periods(current, deadline) <= 0:
        if not is_filed(current):
            return current
        current = _next_period(current)
    return None


def _sync_gstr3b_report_status(gstin, month_or_quarter, year, status):
    frappe.db.set_value(
        "GSTR 3B Report",
        {
            "company_gstin": gstin,
            "month_or_quarter": month_or_quarter,
            "year": year,
        },
        "filing_status",
        status,
    )


# =============================================================================
# ITC Calculation
# =============================================================================


def _is_period_locked(doc):
    return doc.get("itc_claim_period") and _is_gstr3b_filed(
        doc.company_gstin, doc.itc_claim_period
    )


def _calculate_itc_claim_period(
    doc, inward_supply=None, filed=None, ims_action=None, ims_period=None
):
    # already filed
    if filed and doc.itc_claim_period not in filed:
        return None

    # FIRST PREFERENCE: IMS ACTION

    if ims_action in ("Rejected", "Pending"):
        return ""  # clear

    if ims_action == "Accepted" and ims_period:
        return ims_period

    # NEXT PREFERENCE: MATCH FOUND

    if inward_supply and inward_supply.get("ims_action") in ("Rejected", "Pending"):
        return ""  # clear

    # default
    posting_period = format_period(doc.posting_date)
    default_period = posting_period

    if inward_supply and inward_supply.get("return_period_2b"):
        default_period = _max_period(posting_period, inward_supply.return_period_2b)

    return _get_next_unfiled_period(
        doc.company_gstin, default_period, doc.posting_date, filed
    )


def _validate_itc_claim_period(doc):
    period = doc.itc_claim_period
    _validate_period_format(period)

    previous = doc.get_doc_before_save()
    if previous.itc_claim_period != doc.itc_claim_period and (
        _is_gstr3b_filed(doc.company_gstin, previous.itc_claim_period)
        or _is_gstr3b_filed(doc.company_gstin, doc.itc_claim_period)
    ):
        frappe.throw(
            _(
                "Cannot change ITC Claim Period from {0} to {1}. GSTR-3B already filed."
            ).format(previous.itc_claim_period, doc.itc_claim_period)
        )


# =============================================================================
# Bulk Processing
# =============================================================================


def _bulk_update(updates, doctype, source):
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
        content = f"ITC Claim Period {'set to ' + period if period else 'deferred'} via {source}"
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


def _fetch_document_data(doctype, names, only_claim_period_set=False):
    doc = frappe.qb.DocType(doctype)
    query = (
        frappe.qb.from_(doc)
        .select(doc.name, doc.posting_date, doc.company_gstin, doc.itc_claim_period)
        .where(doc.name.isin(names))
    )

    if only_claim_period_set:
        query = query.where(doc.itc_claim_period.isnotnull())

    return query.run(as_dict=True)


def _fetch_inward_supply_data(names):
    GSTR2 = frappe.qb.DocType("GST Inward Supply")
    return (
        frappe.qb.from_(GSTR2)
        .select(GSTR2.name, GSTR2.return_period_2b, GSTR2.ims_action)
        .where(GSTR2.name.isin(names))
        .run(as_dict=True)
    )


def _fetch_linked_documents(invoice_names):
    GSTR2 = frappe.qb.DocType("GST Inward Supply")
    return (
        frappe.qb.from_(GSTR2)
        .select(
            GSTR2.name,
            GSTR2.link_name,
            GSTR2.link_doctype,
            GSTR2.return_period_2b,
            GSTR2.ims_action,
        )
        .where(GSTR2.name.isin(invoice_names))
        .where(GSTR2.link_name.isnotnull())
        .where(GSTR2.link_doctype.isin(SUPPORTED_DOCTYPES))
        .run(as_dict=True)
    )
