# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from india_compliance.gst_india.api_classes.taxpayer_base import (
    TaxpayerBaseAPI,
    otp_handler,
)
from india_compliance.gst_india.utils.gstin_info import (
    get_and_update_filing_preference as create_fiscal_year_logs,
)
from india_compliance.gst_india.utils.gstin_info import (
    get_logs_for_year as get_fiscal_year_logs,
)


class GSTR1Reconciliation(Document):
    @frappe.whitelist()
    @otp_handler
    def generate_gstr1_reconciliation(self):
        if (
            not frappe.db.get_single_value("GST Settings", "enable_api")
            or self.has_all_files()
        ):
            return self.get_reconciliation_summary_data()

        if self.is_gstr1_api_enabled():
            TaxpayerBaseAPI(self.company_gstin).validate_auth_token()

        frappe.enqueue(self._generate_gstr1_reconciliation)
        frappe.msgprint(_("GSTR-1 Reconciliation is being prepared"), alert=True)

    def _generate_gstr1_reconciliation(self):
        if not self.gst_log:
            create_fiscal_year_logs()

        self.create_or_update_gstr1_data()
        self.get_reconciliation_summary_data()

    def create_or_update_gstr1_data(self):
        if not self.gst_log:
            self.get_logs_data()

        for log in self.gst_log:
            if log.status != "Filed":
                continue

            if not log.is_latest_data or not log.filed_summary or log.filed:
                self.create_or_update_gstr_1_data(log.name)

    def create_or_update_gstr_1_data(self, log_name):
        doc = frappe.get_doc("GST Return Log", log_name)

        filters = frappe._dict(
            company=self.company,
            company_gstin=self.company_gstin,
            month_or_quarter=doc.return_period[:2],
            year=doc.return_period[2:],
            filing_preference=doc.filing_preference,
        )

        doc.generate_gstr1_data(filters)

    def has_all_files(self):
        period = f"04{self.fiscal_year.split('-')[0]}"
        self.log_names = get_fiscal_year_logs(self.company_gstin, period, ["GSTR1"])

        self.get_logs_data()

        if len(self.gst_log) != 12:
            self.gst_log = None
            return False

        for log in self.gst_log:
            if log.filing_status != "Filed":
                continue

            if not log.is_latest_data or not log.filed_summary or log.filed:
                return False

        return True

    def is_gstr1_api_enabled(self):
        # this can be changed by moving funcitn to gst settings
        doc = frappe.get_doc("GST Return Log", self.log_names[0])
        return doc.is_gstr1_api_enabled()

    def get_reconciliation_summary_data(self):
        summary_data = {}
        for log in self.gst_log:
            doc = frappe.get_doc("GST Return Log", log.name)
            summary_data[log.name] = doc.get_net_liability_from_amendments()

        return summary_data

    def get_logs_data(self):
        self.gst_log = frappe.get_all(
            "GST Return Log",
            filters={"name": ["in", self.log_names], "gstin": self.company_gstin},
            fields=["name", "is_latest_data", "filed_summary", "filing_status"],
        )
