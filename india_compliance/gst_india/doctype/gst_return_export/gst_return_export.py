# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.background_jobs import is_job_enqueued

from india_compliance.gst_india.api_classes.taxpayer_base import (
    TaxpayerBaseAPI,
    otp_handler,
)
from india_compliance.gst_india.utils import (
    get_periods_between_dates,
    validate_gstin_permission,
)
from india_compliance.gst_india.utils.gstr_utils import ReturnType
from india_compliance.gst_india.utils.returns_export import (
    ReturnAdapter,
    normalize_return_type,
)


class GSTReturnExport(Document):
    """GST Return Export tool — Phase 1 (GSTR-2A / 2B)."""

    @frappe.whitelist()
    @validate_gstin_permission(doctype="GST Return Export")
    @otp_handler
    def sync_return_data(self, company_gstin: str, return_type: str, periods: str | list):
        """Fetch the picked months from the GST portal on a deduplicated job."""
        frappe.has_permission("GST Return Export", "export", throw=True)

        return_type = normalize_return_type(return_type)
        periods = frappe.parse_json(periods) if isinstance(periods, str) else periods

        job_id = f"gst_return_sync:{company_gstin}:{return_type}"
        if is_job_enqueued(job_id):
            return {
                "message": _("A sync is already in progress for GSTIN {0} and {1}.").format(
                    company_gstin, return_type
                ),
            }

        from india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_tool import (
            get_periods_to_download,
        )

        periods = get_periods_to_download(company_gstin, ReturnType(return_type), periods, download_all=True)
        if not periods:
            return {
                "message": _("Nothing to sync — the selected month(s) cannot be re-downloaded."),
                "indicator": "orange",
            }

        # Prompt OTP now (via otp_handler) rather than failing inside the job.
        TaxpayerBaseAPI(company_gstin).validate_auth_token()

        frappe.enqueue(
            _sync_return_data,
            company_gstin=company_gstin,
            return_type=return_type,
            periods=periods,
            queue="long",
            job_id=job_id,
            now=frappe.flags.in_test,
            timeout=1800,
            deduplicate=True,
        )

    @frappe.whitelist()
    @validate_gstin_permission(doctype="GST Return Export")
    def get_summary(self, company_gstin: str, return_type: str, from_date: str, to_date: str):
        """Cumulated headline + one row per selected month (the sync picker)."""
        frappe.has_permission("GST Return Export", "export", throw=True)
        return_type = normalize_return_type(return_type)

        periods = get_periods_between_dates(from_date, to_date)
        adapter = ReturnAdapter.for_return(return_type, company_gstin)
        return {"return_type": return_type, **adapter.get_range_summary(periods)}

    @frappe.whitelist()
    @validate_gstin_permission(doctype="GST Return Export")
    def get_sync_status(self, company_gstin: str, return_type: str, from_date: str, to_date: str):
        """Per-month sync state for the sync picker / missing-sync banner. Delegates to the
        adapter, which reports a month as synced only when its raw payload is stored (what
        the export consumes) — not merely present in the download history."""
        frappe.has_permission("GST Return Export", "export", throw=True)
        return_type = normalize_return_type(return_type)

        periods = get_periods_between_dates(from_date, to_date)
        return ReturnAdapter.for_return(return_type, company_gstin).get_sync_status(periods)


def _sync_return_data(company_gstin, return_type, periods):
    """Background job: fetch the resolved periods, surfacing failures as a toast."""
    adapter = ReturnAdapter.for_return(return_type, company_gstin)
    try:
        adapter.download(periods)
        for period in periods:
            adapter.build_and_store_summary(period)

    except Exception as e:
        frappe.publish_realtime(
            "gstr_2a_2b_download_message",
            {"title": _("Sync Failed"), "message": str(e), "indicator": "red"},
            user=frappe.session.user,
        )
