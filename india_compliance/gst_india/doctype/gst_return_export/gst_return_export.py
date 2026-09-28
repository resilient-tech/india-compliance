# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""Endpoints and delivery: queue, build, save, download, sweep."""

from io import BytesIO
from urllib.parse import quote, urlencode
from zipfile import ZIP_DEFLATED, ZipFile

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
    add_days,
    add_to_date,
    get_datetime,
    get_first_day,
    getdate,
    now,
    now_datetime,
    time_diff_in_seconds,
)

from india_compliance.gst_india.api_classes.taxpayer_base import (
    TaxpayerBaseAPI,
    otp_handler,
)
from india_compliance.gst_india.doctype.gst_return_export.gstr_2_export import EXPORTERS
from india_compliance.gst_india.doctype.gst_return_export.return_adapters import (
    normalize_return_type,
)
from india_compliance.gst_india.doctype.gst_return_export.template_exporter import (
    DEFAULT_GROUP_BY,
    GROUP_BY_ALL,
    GROUP_BY_MONTHS,
    group_periods,
    return_label,
    workbook_name,
)
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    DOCTYPE as RETURN_LOG,
)
from india_compliance.gst_india.doctype.purchase_reconciliation_tool import BaseUtil
from india_compliance.gst_india.utils import (
    create_notification,
    get_periods_between_dates,
    validate_gstin_permission,
)
from india_compliance.gst_india.utils.gstr_utils import ReturnType

EXPORT_READY_EVENT = "gst_return_export_ready"
DOCTYPE = "GST Return Export"
EXPORT_MARKER = "gst_return_export"
BELL_AFTER = 60


class GSTReturnExport(Document):
    @frappe.whitelist()
    @validate_gstin_permission(doctype=DOCTYPE)
    @otp_handler
    def sync_return_data(
        self,
        company_gstin: str,
        return_type: str,
        periods: str | list,
        from_date: str,
        to_date: str,
    ):
        """Fetch picked months from the portal."""
        # validate
        frappe.has_permission(DOCTYPE, "export", throw=True)

        return_type = normalize_return_type(return_type)
        periods = frappe.parse_json(periods) if isinstance(periods, str) else periods

        # only months the portal can serve
        allowed = set(_periods(return_type, from_date, to_date))
        periods = [period for period in periods if period in allowed]

        from india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_tool import (
            get_periods_to_download,
        )

        periods = get_periods_to_download(company_gstin, ReturnType(return_type), periods, download_all=True)
        if not periods:
            return {
                "message": _("Nothing to sync — the selected month(s) cannot be re-downloaded."),
                "indicator": "orange",
            }

        # ask OTP now, not inside the job
        TaxpayerBaseAPI(company_gstin).validate_auth_token()

        # queue
        frappe.enqueue(
            _sync_return_data,
            company_gstin=company_gstin,
            return_type=return_type,
            periods=periods,
            queue="long",
            now=frappe.flags.in_test,
            timeout=1800,
            enqueue_after_commit=True,
        )

    @frappe.whitelist()
    @validate_gstin_permission(doctype=DOCTYPE)
    def get_summary(self, company_gstin: str, return_type: str, from_date: str, to_date: str):
        """Range totals + per-month rows."""
        frappe.has_permission(DOCTYPE, "export", throw=True)
        return_type = normalize_return_type(return_type)

        periods = _periods(return_type, from_date, to_date)
        return get_adapter(return_type, company_gstin).get_range_summary(periods)

    @frappe.whitelist()
    @validate_gstin_permission(doctype=DOCTYPE)
    def get_sync_status(self, company_gstin: str, return_type: str, from_date: str, to_date: str):
        """Per-month sync state for the picker."""
        frappe.has_permission(DOCTYPE, "export", throw=True)
        return_type = normalize_return_type(return_type)

        periods = _periods(return_type, from_date, to_date)
        return get_adapter(return_type, company_gstin).get_sync_status(periods)

    @frappe.whitelist()
    def get_period_bounds(self, return_type: str):
        """First and newest month the portal can serve; the pickers stay inside."""
        frappe.has_permission(DOCTYPE, "export", throw=True)
        return_type = normalize_return_type(return_type)
        return {
            "first": get_exporter(return_type).adapter.first_month,
            "latest": get_first_day(BaseUtil._getdate(ReturnType(return_type))),
        }


def _periods(return_type, from_date, to_date):
    """Months the portal can serve for the range: the return's first month to its cut-off."""
    start = max(getdate(from_date), getdate(get_exporter(return_type).adapter.first_month))
    end = min(getdate(to_date), BaseUtil._getdate(ReturnType(return_type)))
    if start > end:
        frappe.throw(_("No {0} months in the selected range.").format(return_label(return_type)))
    return get_periods_between_dates(start, end)


def _log_names(return_type, gstin, periods):
    return [f"{return_type}-{period}-{gstin}" for period in periods]


def get_exporter(return_type):
    """Exporter for a return type."""
    if exporter := EXPORTERS.get(normalize_return_type(return_type)):
        return exporter
    frappe.throw(_("Export is not supported for {0}").format(return_type))


def get_adapter(return_type, gstin):
    """Adapter for a return type."""
    return get_exporter(return_type).adapter(gstin)


def _sync_return_data(company_gstin, return_type, periods):
    """Job: download, drop exports built on the old data, cache summaries. Toast on failure."""
    adapter = get_adapter(return_type, company_gstin)
    try:
        adapter.download(periods)
        delete_export_files(_log_names(return_type, company_gstin, periods))
        for period in periods:
            adapter.build_and_store_summary(period)
    except Exception as e:
        frappe.publish_realtime(
            "gstr_2a_2b_download_message",
            {"title": _("Sync Failed"), "message": str(e), "indicator": "red"},
            user=frappe.session.user,
        )
        raise e


@frappe.whitelist()
@validate_gstin_permission(doctype=DOCTYPE)
def export_file(
    company_gstin: str,
    return_type: str,
    from_date: str,
    to_date: str,
    group_by: str = DEFAULT_GROUP_BY,
):
    """Queue the build; download fires via realtime when ready."""
    # validate
    frappe.has_permission(DOCTYPE, "export", throw=True)
    return_type = normalize_return_type(return_type)
    periods = _periods(return_type, from_date, to_date)
    group_by = effective_group_by(periods, group_by)

    request = {
        "company_gstin": company_gstin,
        "return_type": return_type,
        "from_date": from_date,
        "to_date": to_date,
        "group_by": group_by,
    }

    # a fresh file already built
    if file := get_reusable_export(company_gstin, return_type, periods, group_by):
        return {"file_name": file.file_name, "created": file.creation, "request": request}

    queued = frappe.enqueue(
        generate_file,
        queue="long",
        timeout=1500,
        job_id=export_file_name(company_gstin, return_type, periods, group_by),
        deduplicate=True,
        company_gstin=company_gstin,
        return_type=return_type,
        from_date=from_date,
        to_date=to_date,
        group_by=group_by,
        user=frappe.session.user,
        requested_at=now(),
    )
    if not queued:
        return {
            "message": _("This export is already being generated. Try again in some time."),
            "indicator": "orange",
        }
    return {"message": _("Generating your export — the download will start when it's ready.")}


def generate_file(
    company_gstin, return_type, from_date, to_date, user, group_by=DEFAULT_GROUP_BY, requested_at=None
):
    """Job: build, save as private File, tell the user."""
    request = {
        "company_gstin": company_gstin,
        "return_type": return_type,
        "from_date": from_date,
        "to_date": to_date,
        "group_by": group_by,
    }
    try:
        periods = _periods(return_type, from_date, to_date)

        # another job may have built it while this one queued
        file = get_reusable_export(company_gstin, return_type, periods, group_by)
        file_name = file.file_name if file else save_file(company_gstin, return_type, periods, group_by)
    except Exception as e:
        frappe.publish_realtime(EXPORT_READY_EVENT, {"error": str(e)}, user=user)
        raise e

    # tell the browser; a slow build also rings the bell, its click downloads the file
    frappe.publish_realtime(
        EXPORT_READY_EVENT, {"file_name": file_name, "request": request}, user=user, after_commit=True
    )
    if time_diff_in_seconds(now(), requested_at or now()) > BELL_AFTER:
        create_notification(
            {"subject": _("{0} is ready to download").format(file_name)},
            DOCTYPE,
            link=f"/api/method/{__name__}.download_export_file?{urlencode(request)}",
        )


def save_file(company_gstin, return_type, periods, group_by):
    """Build, store as private File on a synced log; its stored name."""
    file_name, content = build_export(company_gstin, return_type, periods, group_by)
    stem, ext = file_name.rsplit(".", 1)
    file_name = (
        f"{stem}-{now_datetime():%Y%m%d-%H%M}-{frappe.generate_hash(length=6)}.{ext}"  # moment + unguessable
    )

    # the log's company is what gates the file
    log = frappe.get_all(
        RETURN_LOG,
        filters={
            "name": ("in", _log_names(return_type, company_gstin, periods)),
            "raw_gov_data": ("is", "set"),
        },
        pluck="name",
        limit=1,
    )[0]
    file = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "attached_to_doctype": RETURN_LOG,
            "attached_to_name": log,
            "attached_to_field": export_key(periods, group_by),
            "is_private": 1,
            "content": content,
        }
    )
    file.flags.skip_file_size_check = True  # a year of 2B beats the 25 MB upload cap
    file.insert(ignore_permissions=True)
    return file_name


def build_export(gstin, return_type, periods, group_by=DEFAULT_GROUP_BY):
    """Build the export; (file_name, bytes)."""
    exporter = get_exporter(return_type)
    groups = group_periods(periods, group_by)

    # one workbook
    if len(groups) == 1:
        built = exporter(gstin, groups[0]).build()
        if not built:
            _throw_no_data()
        return built

    # one workbook per group, zipped
    buffer = BytesIO()
    written = 0
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for group in groups:
            if built := exporter(gstin, group).build():
                archive.writestr(*built)
                written += 1

    if not written:
        _throw_no_data()

    return export_file_name(gstin, return_type, periods, group_by), buffer.getvalue()


def _throw_no_data():
    frappe.throw(_("No data to export for the selected period(s). Sync first, then export."))


def effective_group_by(periods, group_by):
    """Known grouping, else the default; a single workbook is "all" however it was asked for."""
    group_by = group_by if group_by in {*GROUP_BY_MONTHS, GROUP_BY_ALL} else DEFAULT_GROUP_BY
    return group_by if len(group_periods(periods, group_by)) > 1 else GROUP_BY_ALL


def export_file_name(gstin, return_type, periods, group_by):
    """Base name for the request. Stored copy adds the build moment, never look up by it."""
    return_type = normalize_return_type(return_type)
    groups = group_periods(periods, group_by)
    if len(groups) == 1:
        return workbook_name(return_type, gstin, groups[0])

    # same range, different grouping = different zip
    return f"{return_label(return_type)}-{gstin}-{periods[0]}_{periods[-1]}-{group_by}.zip"


def export_key(periods, group_by):
    """Request tag on the File. Word characters only, frappe checks."""
    return f"{EXPORT_MARKER}__{group_by}__{periods[0]}__{periods[-1]}"


def get_reusable_export(company_gstin, return_type, periods, group_by):
    """Fresh File row for this exact request, else None. Shared by all allowed the GSTIN."""
    # last sync
    return_type = normalize_return_type(return_type)
    names = _log_names(return_type, company_gstin, periods)
    synced_on = frappe.get_all(
        RETURN_LOG,
        filters={"name": ("in", names), "raw_gov_data": ("is", "set")},
        pluck="modified",
        limit=len(names),
    )
    if not synced_on:
        return None

    # newer than the last sync, at most a day old
    cutoff = max(get_datetime(max(synced_on)), add_to_date(now_datetime(), hours=-24))
    file = frappe.db.get_value(
        "File",
        {
            "attached_to_doctype": RETURN_LOG,
            "attached_to_name": ("in", names),
            "attached_to_field": export_key(periods, group_by),
            "is_private": 1,
            "creation": (">", cutoff),
        },
        ["file_name", "file_url", "creation"],
        order_by="creation desc",
        as_dict=True,
    )

    # named for this request
    stem = export_file_name(company_gstin, return_type, periods, group_by).rsplit(".", 1)[0]
    return file if file and (file.file_url or "").startswith(f"/private/files/{stem}") else None


@frappe.whitelist()
@validate_gstin_permission(doctype=DOCTYPE)
def download_export_file(
    company_gstin: str,
    return_type: str,
    from_date: str,
    to_date: str,
    group_by: str = DEFAULT_GROUP_BY,
):
    """Stream the file built for this request. Client names the request, never a file."""
    # validate
    frappe.has_permission(DOCTYPE, "export", throw=True)
    return_type = normalize_return_type(return_type)
    periods = _periods(return_type, from_date, to_date)
    group_by = effective_group_by(periods, group_by)
    file = get_reusable_export(company_gstin, return_type, periods, group_by)
    if not file:
        frappe.throw(
            _("This export is no longer available. Please export again."),
            frappe.DoesNotExistError,
        )

    # stream
    from frappe.core.doctype.access_log.access_log import make_access_log
    from frappe.utils.response import send_private_file

    make_access_log(doctype=RETURN_LOG, document=file.file_name, file_type=file.file_name.rsplit(".", 1)[-1])
    response = send_private_file(file.file_url.split("/private", 1)[1], filename=file.file_name)
    response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(file.file_name)}"
    return response


def delete_export_files(log_names=None):
    """Drop the exports built on these logs; with none named (the daily job), the day-old ones."""
    scope = (
        {"attached_to_name": ("in", log_names)}
        if log_names
        else {"creation": ("<", add_days(now_datetime(), -1))}
    )
    files = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": RETURN_LOG,
            "attached_to_field": ("like", f"{EXPORT_MARKER}%"),
            **scope,
        },
        pluck="name",
    )
    frappe.delete_doc("File", files, ignore_permissions=True, delete_permanently=True)
