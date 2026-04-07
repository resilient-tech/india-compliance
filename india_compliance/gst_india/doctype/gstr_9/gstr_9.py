# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from india_compliance.gst_india.api_classes.taxpayer_base import otp_handler
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    get_gst_return_log,
)
from india_compliance.gst_india.utils.gstr_9 import (
    PORTAL_SOURCED_ROWS,
    aggregate_books,
    compute_auto_rows,
    get_fy_dates,
    get_fy_period,
)


class GSTR9(Document):
    @frappe.whitelist()
    def generate_gstr9(self):
        """
        Permission check not required as user has access to doc.
        Validates inputs and enqueues GSTR-9 data generation.
        """
        period = get_fy_period(self.financial_year)
        log_name = f"GSTR9-{period}-{self.company_gstin}"

        gstr9_log = get_gst_return_log(log_name, company=self.company)

        if gstr9_log.status == "In Progress":
            frappe.msgprint(
                _("GSTR-9 is being prepared. Please wait for the process to complete."),
                title=_("GSTR-9 Generation In Progress"),
            )
            return

        if gstr9_log.is_latest_data and gstr9_log.get("books"):
            data = gstr9_log.get_gstr9_data()
            if data:
                return data

        gstr9_log.update_status("In Progress")
        frappe.enqueue(
            self._generate_gstr9,
            queue="long",
            enqueue_after_commit=True,
        )

        frappe.msgprint(_("GSTR-9 is being prepared"), alert=True)

    @frappe.whitelist()
    def recompute_books(self):
        """
        Permission check not required as user has access to doc.
        Forces recomputation of books data.
        """
        period = get_fy_period(self.financial_year)
        log_name = f"GSTR9-{period}-{self.company_gstin}"

        gstr9_log = get_gst_return_log(log_name, company=self.company)
        gstr9_log.remove_json_for("books")

        return self.generate_gstr9()

    @frappe.whitelist()
    @otp_handler
    def download_portal_data(self):
        """
        Download auto-drafted GSTR-9 data from GST portal, update comparison,
        and return the merged data for frontend display.
        """
        settings = frappe.get_cached_doc("GST Settings")
        if not settings.is_gstr9_api_enabled(self.company_gstin):
            frappe.throw(_("GSTR-9 API features are not enabled in GST Settings."))
        period = get_fy_period(self.financial_year)
        log_name = f"GSTR9-{period}-{self.company_gstin}"

        gstr9_log = get_gst_return_log(log_name, company=self.company)

        books_data = gstr9_log.get_json_for("books")
        if not books_data:
            frappe.throw(
                _(
                    "Please generate GSTR-9 books data first before downloading portal data."
                )
            )

        from_date, to_date = get_fy_dates(self.financial_year)
        filters = frappe._dict(
            company=self.company,
            company_gstin=self.company_gstin,
            financial_year=self.financial_year,
            from_date=from_date,
            to_date=to_date,
        )

        gstr9_log.remove_json_for("unfiled")

        portal_data = gstr9_log._get_gstr9_portal_data(filters)
        if not portal_data:
            frappe.throw(
                _(
                    "Failed to download portal data from GSTN. "
                    "Please check your API connection and credentials."
                )
            )

        row_data = aggregate_books(books_data)

        # Merge portal-sourced rows into books before computing auto rows
        for row_key in PORTAL_SOURCED_ROWS:
            if row_key in portal_data:
                row_data[row_key] = portal_data[row_key]

        compute_auto_rows(row_data)
        compute_auto_rows(portal_data)

        gstr9_log._compare_books_and_portal(row_data, portal_data)
        gstr9_log._summarize_gstr9_data({"row_data": row_data, "portal": portal_data})

        return gstr9_log.get_gstr9_data()

    def _generate_gstr9(self):
        """Wrapper that runs in background queue."""
        period = get_fy_period(self.financial_year)
        log_name = f"GSTR9-{period}-{self.company_gstin}"
        gstr9_log = get_gst_return_log(log_name, company=self.company)

        from_date, to_date = get_fy_dates(self.financial_year)

        filters = frappe._dict(
            company=self.company,
            company_gstin=self.company_gstin,
            financial_year=self.financial_year,
            from_date=from_date,
            to_date=to_date,
        )

        try:
            gstr9_log.generate_gstr9_data(filters, callback=self.on_generate)
        except Exception as e:
            gstr9_log.update_status("Failed", commit=True)

            frappe.publish_realtime(
                "gstr9_generation_failed",
                message={"error": str(e), "filters": filters},
                user=frappe.session.user,
            )
            raise

    def on_generate(self, filters=None):
        """Publish realtime event when generation completes."""
        period = get_fy_period(self.financial_year)
        log_name = f"GSTR9-{period}-{self.company_gstin}"

        if frappe.db.exists("GST Return Log", log_name):
            frappe.db.set_value(
                "GST Return Log",
                log_name,
                {"generation_status": "Generated", "is_latest_data": 1},
            )

        frappe.publish_realtime(
            "gstr9_data_prepared",
            message={"filters": filters or self},
            user=frappe.session.user,
        )


@frappe.whitelist()
def get_gstr9_invoice_detail(company_gstin: str, financial_year: str, row_key: str):
    """
    Return individual invoice / bill records for the given GSTR-9 row.
    Reads from stored books data to ensure consistency with the generated snapshot.
    """
    frappe.has_permission("GSTR-9", throw=True)

    from india_compliance.gst_india.utils.gstr_9 import PURCHASE_ROW_KEYS

    period = get_fy_period(financial_year)
    log_name = f"GSTR9-{period}-{company_gstin}"

    gstr9_log = get_gst_return_log(log_name)
    books = gstr9_log.get_json_for("books")

    if not books:
        frappe.throw(_("Please generate GSTR-9 data first."))

    # Parent rows (6B, 6C, 6D, 6E) combine sub-row invoice lists
    _PARENT_SUB_ROWS = {
        "6B": ["6B_ip", "6B_cg", "6B_is"],
        "6C": ["6C_ip", "6C_cg", "6C_is"],
        "6D": ["6D_ip", "6D_cg", "6D_is"],
        "6E": ["6E_ip", "6E_cg"],
    }

    if row_key in _PARENT_SUB_ROWS:
        invoices = []
        for sub_key in _PARENT_SUB_ROWS[row_key]:
            sub_value = books.get(sub_key, [])
            if isinstance(sub_value, list):
                invoices.extend(sub_value)
        return {"is_purchase": row_key in PURCHASE_ROW_KEYS, "data": invoices}

    value = books.get(row_key)
    if isinstance(value, list):
        return {"is_purchase": row_key in PURCHASE_ROW_KEYS, "data": value}

    return {"is_purchase": False, "data": []}
