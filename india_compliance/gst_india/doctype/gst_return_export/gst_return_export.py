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
from india_compliance.gst_india.utils.gstr_utils import ReturnType

GST_RETURN_TO_RETURN_TYPE = {
    "GSTR-2A": ReturnType.GSTR2A.value,
    "GSTR-2B": ReturnType.GSTR2B.value,
}


class GSTReturnExport(Document):
    """GST Return Export tool — Phase 1 (GSTR-2A / 2B)."""

    @frappe.whitelist()
    @otp_handler
    def sync_return_data(self, company_gstin: str, return_type: str, date_range: str | list):
        """Fetch the selected return from the GST portal on a deduplicated job."""
        frappe.has_permission("GST Return Export", "export", throw=True)

        return_type = GST_RETURN_TO_RETURN_TYPE.get(return_type, return_type)

        job_id = f"gst_return_export:{company_gstin}:{return_type}"
        if is_job_enqueued(job_id):
            return {
                "message": _("A sync is already in progress for GSTIN {0} and {1}.").format(
                    company_gstin, return_type
                ),
            }

        periods = get_periods_to_sync(company_gstin, return_type, date_range)
        if not periods:
            return {
                "message": _(
                    "Nothing to sync — the selected period(s) are not yet"
                    " available on the portal or cannot be re-downloaded."
                ),
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
    def get_summary(self, company_gstin: str, return_type: str, date_range: str | list):
        """Read the prepared per-period summary(ies) for the current selection."""
        frappe.has_permission("GST Return Export", "export", throw=True)
        return_type = GST_RETURN_TO_RETURN_TYPE.get(return_type, return_type)

        from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
            BaseUtil,
        )
        from india_compliance.gst_india.utils.returns_export import ReturnExporter

        periods = BaseUtil.get_periods(date_range, ReturnType(return_type), company_gstin)
        exporter = ReturnExporter.for_return(return_type, company_gstin)
        return {"return_type": return_type, "summaries": exporter.get_summaries(periods)}


def get_periods_to_sync(company_gstin, return_type, date_range):
    """Periods GSTN can serve now, minus frozen-2B / quarterly ones."""
    from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
        BaseUtil,
    )
    from india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_tool import (
        get_periods_to_download,
    )

    return_type = ReturnType(return_type)
    periods = BaseUtil.get_periods(date_range, return_type, company_gstin)
    return get_periods_to_download(company_gstin, return_type, periods, download_all=True)


def _sync_return_data(company_gstin, return_type, periods):
    """Background job: fetch the resolved periods, surfacing failures as a toast."""
    from india_compliance.gst_india.utils.returns_export import ReturnExporter

    exporter = ReturnExporter.for_return(return_type, company_gstin)
    try:
        exporter.download(periods)
        for period in periods:
            exporter.build_and_store_summary(period)

    except Exception as e:
        frappe.publish_realtime(
            "gstr_2a_2b_download_message",
            {"title": _("Sync Failed"), "message": str(e), "indicator": "red"},
            user=frappe.session.user,
        )
