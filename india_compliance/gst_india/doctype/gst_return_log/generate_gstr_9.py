# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt

from india_compliance.gst_india.utils.gstr_9 import (
    AMOUNT_FIELDS,
    PORTAL_SOURCED_ROWS,
    GSTR9_Row,
    _empty_row,
    aggregate_books,
    compute_auto_rows,
    get_fy_schema,
)


class SummarizeGSTR9:
    """Builds a summary list from GSTR-9 row data for frontend display."""

    def get_summarized_data(self, data, financial_year):
        summary = []

        for row_key, description in get_fy_schema(financial_year).descriptions.items():
            row_data = data.get(row_key, _empty_row())

            if row_key in (GSTR9_Row.TABLE_9, GSTR9_Row.TABLE_14, GSTR9_Row.TABLE_15):
                summary.append(
                    {
                        "row_key": row_key,
                        "description": description,
                        "rows": row_data if isinstance(row_data, list) else [],
                    }
                )
                continue

            if row_key in (GSTR9_Row.TABLE_17, GSTR9_Row.TABLE_18):
                summary.append(self._hsn_summary_row(row_key, description, row_data))
                continue

            entry = {
                "row_key": row_key,
                "description": description,
            }

            for field in AMOUNT_FIELDS:
                entry[field] = flt(row_data.get(field, 0), 2)

            summary.append(entry)

        return summary

    def _hsn_summary_row(self, row_key, description, items):
        """Aggregate HSN item list into a summary row with Goods/Services split."""
        totals = _empty_row()

        goods_list = (items or {}).get("goods") or []
        services_list = (items or {}).get("services") or []
        all_items = goods_list + services_list

        for item in all_items:
            for field in AMOUNT_FIELDS:
                totals[field] += flt(item.get(field, 0))

        return {
            "row_key": row_key,
            "description": description,
            "no_of_records": len(all_items),
            "goods": goods_list,
            "services": services_list,
            **{f: flt(totals[f], 2) for f in AMOUNT_FIELDS},
        }


class GenerateGSTR9(SummarizeGSTR9):
    """Mixin for GSTReturnLog: GSTR-9 data generation and portal comparison.

    Handles data generation, auto-computation, optional portal download,
    and books-vs-portal reconciliation.
    """

    def get_gstr9_data(self):
        """Load already-generated GSTR-9 data from attachments."""
        books_summary = self.get_json_for("books_summary")
        if not books_summary:
            return

        data = {"books_summary": books_summary}

        if portal_summary := self.get_json_for("unfiled_summary"):
            data["portal_summary"] = portal_summary

        if comparison := self.get_json_for("reconcile"):
            data["comparison"] = comparison

        data["status"] = self.filing_status or "Not Filed"
        self.update_status("Generated")
        return data

    def generate_gstr9_data(self, filters, callback=None):
        """
        Generate GSTR-9 Data.

        Steps:
        1. Compute books data (invoice-level with classification)
        2. Aggregate invoices → row-level amounts
        3. Compute auto-calculated sub-totals
        4. Summarize and save
        5. Optionally fetch portal data and compare
        """
        data = {}

        books = self._get_gstr9_books_data(filters)
        fy = filters.get("financial_year")

        # Aggregate invoice lists → row-level amount dicts for auto-compute
        row_data = aggregate_books(books, fy)
        compute_auto_rows(row_data, fy)
        data["row_data"] = row_data

        # Check if portal APIs are enabled
        settings = frappe.get_cached_doc("GST Settings")

        if settings.is_gstr9_api_enabled(self.gstin, warn_for_missing_credentials=True):
            try:
                portal_data = self._get_gstr9_portal_data(filters)
                if portal_data:
                    for row_key in PORTAL_SOURCED_ROWS:
                        if row_key in portal_data:
                            row_data[row_key] = portal_data[row_key]

                    compute_auto_rows(row_data, fy)
                    compute_auto_rows(portal_data, fy)
                    data["portal"] = portal_data
                    data["comparison"] = self._compare_books_and_portal(row_data, portal_data)
            except Exception:
                frappe.log_error(
                    title="GSTR-9 Portal Data Download Failed",
                    message=frappe.get_traceback(),
                )

        # Summarize and strip raw data from response
        self._summarize_gstr9_data(data, fy)
        data.pop("row_data", None)
        data.pop("portal", None)
        data["status"] = self.filing_status or "Not Filed"

        return callback and callback(filters)

    def _get_gstr9_books_data(self, filters):
        """Compute or load cached invoice-level books data."""
        if self.is_latest_data and self.get("books"):
            books = self.get_json_for("books")
            if books:
                return books

        from india_compliance.gst_india.utils.gstr_9.gstr_9_data import GSTR9BooksData

        books = GSTR9BooksData(filters).get_data()
        self.update_json_for("books", books, reset_reconcile=True)
        return books

    def _get_gstr9_portal_data(self, filters):
        """Download or load cached portal auto-drafted data."""
        if self.is_latest_data and self.get("unfiled"):
            portal_data = self.get_json_for("unfiled")
            if portal_data:
                return portal_data

        from india_compliance.gst_india.utils.gstr_9.gstr_9_download import (
            download_gstr9_data,
        )

        portal_data = download_gstr9_data(self, filters)
        if portal_data:
            self.update_json_for("unfiled", portal_data)

        return portal_data

    def _compare_books_and_portal(self, books_data, portal_data):
        """Compare books data with portal data row by row."""
        comparison = {}

        all_rows = set(books_data.keys()) | set(portal_data.keys())

        for row_key in all_rows:
            # Skip HSN detail lists, nested-list rows, and metadata keys
            if row_key in (
                GSTR9_Row.TABLE_9,
                GSTR9_Row.TABLE_14,
                GSTR9_Row.TABLE_15,
                GSTR9_Row.TABLE_17,
                GSTR9_Row.TABLE_18,
                "creation",
            ):
                continue

            books_row = books_data.get(row_key, _empty_row())
            portal_row = portal_data.get(row_key, _empty_row())

            diff = _empty_row()
            has_diff = False

            for field in AMOUNT_FIELDS:
                diff[field] = flt(books_row.get(field, 0), 2) - flt(portal_row.get(field, 0), 2)
                if diff[field] != 0:
                    has_diff = True

            if has_diff:
                comparison[row_key] = {
                    "books": books_row,
                    "portal": portal_row,
                    "difference": diff,
                }

        if comparison:
            self.update_json_for("reconcile", comparison)

        return comparison

    def _summarize_gstr9_data(self, data, financial_year):
        """Summarize aggregated row data (and optionally portal) for frontend."""
        if row_data := data.get("row_data"):
            summary = self.get_summarized_data(row_data, financial_year)
            self.update_json_for("books_summary", summary)
            data["books_summary"] = summary

        if portal := data.get("portal"):
            summary = self.get_summarized_data(portal, financial_year)
            self.update_json_for("unfiled_summary", summary)
            data["portal_summary"] = summary
