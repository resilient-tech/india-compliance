# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_to_date, getdate

from india_compliance.gst_india.api_classes.taxpayer_base import (
    TaxpayerBaseAPI,
    otp_handler,
)
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    get_gst_return_log,
)


class GSTR1Reconciliation(Document):

    @frappe.whitelist()
    @otp_handler
    def get_gstr_1_reconciliation(self):
        """
        Inputs: company, company_gstin, fiscal_year
        Outputs: gstr_1_reconciliation
        Steps:
        1. Get the fiscal year date range from the Fiscal Year doctype
        2. For each month/quarter in the fiscal year:
        3. Get the GSTR-1 reconciliation data from GSTR-1 Return Log if it is latest and exists
        4. If not, call the GSTR-1 API to fetch the data
        5. Reconcile the books and gov data
        6. Summarize the data
        7. Store the data in GST Return Log
        8. Return the aggregated data of each month/quarter
        """

        settings = frappe.get_doc("GST Settings")

        if not settings.is_gstr1_api_enabled(
            self.company_gstin, warn_for_missing_credentials=True
        ):
            frappe.throw("GSTR-1 API is not enabled for this GSTIN")

        year_date_range = frappe.get_value(
            "Fiscal Year", self.fiscal_year, ["year_start_date", "year_end_date"]
        )
        if not year_date_range:
            frappe.throw(f"Fiscal Year {self.fiscal_year} not found")

        year_start_date, year_end_date = year_date_range

        gstr_logs = self.get_gstr_logs(year_start_date, year_end_date)

        # Let's assume all the logs are present and latest

        data = {"reconcile": [], "reconcile_summary": []}
        for gstr_log in gstr_logs:
            _data = {"reconcile": [], "reconcile_summary": []}

            filters = self._get_filters(gstr_log)
            books_data = gstr_log.get_books_gstr1_data(gstr_log)

            try:
                gov_data, is_queued = gstr_log.get_gov_gstr1_data()
            except frappe.ValidationError as error:
                frappe.throw(title="GSTR-1 Generation Failed", msg=str(error))

            # check the usage of is_queued

            reconcile_data = gstr_log.get_reconciled_gstr1_data(gov_data, books_data)
            reconcile_data = gstr_log.normalize_data(reconcile_data)
            _data["reconcile"].extend(reconcile_data)

            gstr_log.summarize_data(_data, filters)

            for key in _data:
                data[key].extend(_data[key])

        data["reconcile_summary"] = self.summarize_data(data["reconcile_summary"])
        return data

    def _get_filters(self, gstr_log):
        return frappe._dict(
            company=self.company,
            company_gstin=self.company_gstin,
            month_or_quarter=gstr_log.return_period[:2],
            year=gstr_log.return_period[2:],
            filing_preference=gstr_log.filing_preference,
        )

    def get_gstr_logs(self, year_start_date, year_end_date):
        """
        Retrieve the latest GSTR-1 reconciliation logs for each month in the fiscal year, if available.
        """
        gstr_logs = []
        current_date = year_start_date
        now_date = getdate()
        # Ensure we do not go beyond the current date in the current year
        if year_end_date.year == now_date.year:
            last_date = now_date

        while current_date <= last_date:
            period = current_date.strftime("%m%Y")
            log_name = f"GSTR-1-{period}-{self.company_gstin}"

            gstr_logs.append(get_gst_return_log(log_name))

            # Move to the next month
            current_date = add_to_date(current_date, months=1)

        return gstr_logs

    def summarize_data(self, data):
        """
        Summarize the data for the given filters (Aggregate the data)
        """
        pass
