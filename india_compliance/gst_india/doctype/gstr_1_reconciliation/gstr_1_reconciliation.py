# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _, cint
from frappe.model.document import Document

from india_compliance.gst_india.api_classes.taxpayer_base import (
    TaxpayerBaseAPI,
    otp_handler,
)
from india_compliance.gst_india.utils import MONTHS
from india_compliance.gst_india.utils.gstin_info import (
    get_and_update_filing_preference as create_fiscal_year_logs,
)
from india_compliance.gst_india.utils.gstin_info import (
    get_logs_for_year as get_fiscal_year_logs,
)
from india_compliance.gst_india.utils.gstr_1 import (
    CATEGORY_SUB_CATEGORY_MAPPING,
    GSTR1_SubCategory,
)


class GSTR1Reconciliation(Document):
    AMOUNT_FIELDS = {
        "total_taxable_value": 0,
        "total_igst_amount": 0,
        "total_cgst_amount": 0,
        "total_sgst_amount": 0,
        "total_cess_amount": 0,
    }

    def validate(self):
        self.generate_gstr1_reconciliation()

    @frappe.whitelist()
    @otp_handler
    def generate_gstr1_reconciliation(self):
        settings = frappe.get_cached_doc("GST Settings")

        if not settings.enable_api or self.has_all_files():
            return self.get_reconciliation_data()

        # TODO: first setting pr should merge
        if settings.is_gstr1_api_enabled(settings):
            TaxpayerBaseAPI(self.company_gstin).validate_auth_token()

        frappe.enqueue(self._generate_gstr1_reconciliation)
        frappe.msgprint(_("GSTR-1 Reconciliation is being prepared"), alert=True)

    def _generate_gstr1_reconciliation(self):
        if not self.gst_log:
            period = f"04{self.fiscal_year.split('-')[0]}"
            create_fiscal_year_logs(self.company_gstin, period)

        self.create_or_update_gstr1_data()
        self.get_reconciliation_data()

    def create_or_update_gstr1_data(self):
        if not self.gst_log:
            self.get_logs_info()

        for log in self.gst_log:
            if (
                log.filing_status == "Filed"
                and log.is_latest_data
                and log.filed_summary
            ):
                continue

            self.create_or_update_gstr_1_data(log.name)

    def create_or_update_gstr_1_data(self, log_name):
        doc = frappe.get_doc("GST Return Log", log_name)

        filters = frappe._dict(
            company=self.company,
            company_gstin=self.company_gstin,
            month_or_quarter=MONTHS[cint(doc.return_period[:2]) - 1],
            year=doc.return_period[2:],
            filing_preference=doc.filing_preference,
        )

        doc.generate_gstr1_data(filters)

    def has_all_files(self):
        period = f"04{self.fiscal_year.split('-')[0]}"
        self.log_names = get_fiscal_year_logs(self.company_gstin, period, ["GSTR1"])
        self.get_logs_info()

        if len(self.gst_log) != 12:
            self.gst_log = None
            return False

        # TODO : check that untill which log i have to check this as it is possible that
        # for february it is not filed then this will return False but it should return true
        for log in self.gst_log:
            if (
                log.filing_status == "Filed"
                and log.is_latest_data
                and log.filed_summary
            ):
                continue

            return False

        return True

    def get_reconciliation_data(self):
        reconcile_data = self.get_invoice_detail_data()
        reconcile_summary = self.get_reconciliation_summary_data()

        data = {
            "reconcile_data": reconcile_data,
            "reconcile_summary": reconcile_summary,
        }

        print(data, "data")
        return data

    def get_invoice_detail_data(self):
        reconciled_invoices = {}

        for log in self.gst_log:
            doc = frappe.get_doc("GST Return Log", log.name)
            reconcile_data = doc.get_json_for("reconcile")

            for subcategory in GSTR1_SubCategory:
                subcategory = subcategory.value
                if subcategory not in reconcile_data:
                    continue

                invoices = reconcile_data[subcategory]
                reconciled_invoices.setdefault(subcategory, [])

                for invoice in invoices.values():
                    reconciled_invoices[subcategory].append(
                        {
                            "month": doc.get("return_period"),
                            **invoice,
                        }
                    )

        return reconciled_invoices

    def get_reconciliation_summary_data(self):
        subcategory_summary = {}
        net_liability = {
            "description": "Net Liability from Amendments",
            "indent": 0,
            **self.AMOUNT_FIELDS,
        }

        for log in self.gst_log:
            doc = frappe.get_doc("GST Return Log", log.name)
            reconcile_summary = doc.get_json_for("reconcile").get("summary", {})

            self.get_subcategory_summary(reconcile_summary, subcategory_summary)

            liability = doc.get_net_liability_from_amendments() or {}
            for key, value in liability.items():
                if key in self.AMOUNT_FIELDS:
                    net_liability[key] += value

        overall_summary = self.get_overall_summary(subcategory_summary)
        overall_summary.append(net_liability)

        return overall_summary

    def get_subcategory_summary(self, reconcile_summary, subcategory_summary):
        for subcategory in GSTR1_SubCategory:
            subcategory = subcategory.value + " (Amended)"
            subcategory_data = reconcile_summary.get(subcategory)

            if not subcategory_data:
                continue

            subcategory_summary.setdefault(
                subcategory, self.default_subcategory_summary(subcategory)
            )

            _data = reconcile_summary.get(subcategory, {})
            for key in self.AMOUNT_FIELDS:
                subcategory_summary[subcategory][key] += _data.get(key, 0)

            subcategory_summary[subcategory]["no_of_records"] += _data.get(
                "no_of_records", 0
            )

    def default_subcategory_summary(self, subcategory):
        return {
            "description": subcategory,
            "no_of_records": 0,
            "indent": 1,
            **self.AMOUNT_FIELDS,
        }

    def get_overall_summary(self, subcategory_summary):
        cateogory_summary = []
        for category, sub_categories in CATEGORY_SUB_CATEGORY_MAPPING.items():
            category = category.value
            summary_row = {
                "description": category,
                "no_of_records": 0,
                "indent": 0,
                **self.AMOUNT_FIELDS,
            }

            cateogory_summary.append(summary_row)
            remove_category_row = True

            for subcategory in sub_categories:
                subcategory = subcategory.value + " (Amended)"
                subcategory_row = subcategory_summary.get(subcategory)
                if not subcategory_row:
                    continue

                summary_row["no_of_records"] += subcategory_row["no_of_records"] or 0
                for key in self.AMOUNT_FIELDS:
                    summary_row[key] += subcategory_row[key]

                cateogory_summary.append(subcategory_row)
                remove_category_row = False

            if remove_category_row:
                cateogory_summary.remove(summary_row)

        return cateogory_summary

    def get_logs_info(self):
        # TODO : change here
        self.log_names = ["GSTR1-112024-24AAUPV7468F1ZW"]

        self.gst_log = frappe.get_all(
            "GST Return Log",
            filters={"name": ["in", self.log_names], "gstin": self.company_gstin},
            fields=["name", "is_latest_data", "filed_summary", "filing_status"],
        )
