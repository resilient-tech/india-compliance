# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from india_compliance.gst_india.api_classes.taxpayer_base import (
    otp_handler,
)
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    get_gst_return_log,
)
from india_compliance.gst_india.utils import get_month_or_quarter_dict
from india_compliance.gst_india.utils.gstr_1 import GSTR1_SubCategory
from india_compliance.gst_india.utils.gstr_utils import ReturnType

MONTHS = {v: k for k, v in get_month_or_quarter_dict().items()}


class GSTR1Reconciliation(Document):

    @frappe.whitelist()
    @otp_handler
    def get_gstr_1_reconciliation(self, recompute=False):
        self.settings = frappe.get_doc("GST Settings")

        if not self.settings.is_gstr1_api_enabled(
            self.company_gstin, warn_for_missing_credentials=True
        ):
            frappe.throw("GSTR-1 API is not enabled for this GSTIN")

        fiscal_year_period = "".join(self.fiscal_year.split("-"))
        log_name = (
            f"{ReturnType.GSTR1R.value}-{fiscal_year_period}-{self.company_gstin}"
        )

        gstr1_reco_log = get_gst_return_log(
            log_name, company=self.company, filing_status="Filed"
        )

        message = None
        if gstr1_reco_log.status == "In Progress":
            message = "GSTR-1 Reconciliation is being prepared. Please wait for the process to complete."

        elif gstr1_reco_log.status == "Queued":
            message = "GSTR-1 Reconciliation download is queued and could take some time. Please wait for the process to complete."

        if message:
            frappe.msgprint(
                _(message), title=_("GSTR-1 Reconciliation Generation In Progress")
            )
            return

        if recompute:
            gstr1_reco_log.remove_json_for("reconcile")

        fields = [
            "reconcile",
            "reconcile_summary",
        ]

        if gstr1_reco_log.is_latest_data and all(
            getattr(gstr1_reco_log, field, None) for field in fields
        ):
            data = gstr1_reco_log.load_data(**fields)

            if data:
                return data

        self.gstr1_reco_log = gstr1_reco_log

        gstr1_reco_log.update_status("In Progress")
        frappe.enqueue(
            self._generate_gstr1_reconciliation,
            queue="short",
            recompute=recompute,
            callback=self.on_generate_gstr1_reconciliation,
        )

        if not message:
            message = "GSTR-1 Reconciliation is being prepared"

        frappe.msgprint(_(message), alert=True)

    def on_generate_gstr1_reconciliation(self):
        if self.errors:
            error_messages = "\n".join(
                [f"{error.name}: {error.message}" for error in self.errors]
            )
            frappe.throw(
                _("Errors occurred while generating GSTR-1 Reconciliation: {0}").format(
                    error_messages
                )
            )

        self.gstr1_reco_log.db_set(
            {
                "generation_status": "Generated",
                "is_latest_data": True,
            }
        )

        frappe.publish_realtime(
            "gstr1_reconciliation_prepared",
            message={
                "filters": {
                    "company": self.company,
                    "fiscal_year": self.fiscal_year,
                    "company_gstin": self.company_gstin,
                },
                "errors": [],
            },
            user=frappe.session.user,
        )

    def _generate_gstr1_reconciliation(self, recompute=False, callback=None):
        data = {}

        start_date, end_date = frappe.get_value(
            "Fiscal Year", self.fiscal_year, ["year_start_date", "year_end_date"]
        )

        gstr_log = self.get_gstr_logs(start_date, end_date)

        books_data, gov_data = self.get_data(gstr_log, recompute)

        reconcile = self.gstr1_reco_log.get_reconcile_gstr1_data(gov_data, books_data)

        data["reconcile"] = self.gstr1_reco_log.normalize_data(reconcile)
        data["filed"] = self.gstr1_reco_log.normalize_data(gov_data)
        data["books"] = self.gstr1_reco_log.normalize_data(books_data)

        self.gstr1_reco_log.filing_status = "Filed"
        self.gstr1_reco_log.summarize_data(data, frappe._dict(filing_from=start_date))

        return callback and callback()

    def get_data(self, gstr_log, recompute=False):
        books_data, gov_data = frappe._dict(), frappe._dict()
        self.errors = []
        for period, log in gstr_log.values():
            if not log:
                log_name = f"{ReturnType.GSTR1.value}-{period}-{self.company_gstin}"
                log = get_gst_return_log(log_name, insert=False)
                gstr_log[period] = log

            if recompute:
                log.remove_json_for("books")

            _books_data, _gov_data = self._get_gstr1_data(period, log)

            self.aggregate_data(_books_data, books_data)
            self.aggregate_data(_gov_data, gov_data)

        return books_data, gov_data

    def _get_gstr1_data(self, period, log):
        if log.is_latest_data and log.has_all_files(settings=self.settings):
            data = log.get_gstr1_data()

            if data:
                return data.get("books", frappe._dict()), data.get(
                    "filed", frappe._dict()
                )

        filters = self._get_filters(period, log)

        try:
            return log.generate_gstr1_data(filters, callback=self.on_generate_gstr1)

        except frappe.ValidationError as e:
            self.errors.append(e)

    def _get_filters(self, period, log):
        month_or_quarter = (
            MONTHS.get(period[:2]) if log.filing_preference == "Monthly" else period[:2]
        )

        return frappe._dict(
            company=self.company,
            company_gstin=self.company_gstin,
            month_or_quarter=month_or_quarter,
            year=period[2:],
            filing_preference=log.filing_preference,
            gstr_log=log,
        )

    def on_generate_gstr1(self, filters=None, error_log=None):
        if not filters:
            return

        if error_log:
            # send error
            print(
                f"Error while generating GSTR-1 for {filters.company_gstin} for period {filters.month_or_quarter}-{filters.year}: {error_log}"
            )
            return

        gstr_log = filters.get("gstr_log", None)

        assert gstr_log, "GSTR Log is required to generate GSTR-1 Reconciliation"

        return gstr_log.get("books", frappe._dict()), gstr_log.get(
            "filed", frappe._dict()
        )

    def get_gstr_logs(self, start_date, end_date):
        monthly_periods = self._get_periods(start_date, end_date)
        quarterly_periods = [
            monthly_period
            for monthly_period in monthly_periods
            if int(monthly_period[:2]) % 3 == 0
        ]

        gstr_logs = frappe._dict()
        start_period_index = 0
        for quarterly_period in quarterly_periods:
            index = monthly_periods.index(quarterly_period)

            log = self._get_gstr_log(quarterly_period)
            gstr_logs[quarterly_period] = log

            if log and log.filing_preference == "Quarterly":
                start_period_index = index + 1
                continue

            periods = monthly_periods[start_period_index:index]

            for period in periods:
                gstr_logs[period] = self._get_gstr_log(period)

            start_period_index = index + 1

        for period in monthly_periods[start_period_index:]:
            gstr_logs[period] = self._get_gstr_log(period)

        return gstr_logs

    def _get_periods(self, start_date, end_date):
        periods = []
        current_year = start_date.year
        current_month = start_date.month

        now_date = getdate()
        if now_date < end_date:
            end_date = now_date

        while (current_year < end_date.year) or (
            current_year == end_date.year and current_month <= end_date.month
        ):
            periods.append(f"{current_month:02d}{current_year}")
            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1

        return periods

    def _get_gstr_log(self, period):
        log_name = f"{ReturnType.GSTR1.value}-{period}-{self.company_gstin}"
        try:
            return frappe.get_doc("GST Return Log", log_name)
        except frappe.DoesNotExistError:
            return None

    def aggregate_data(self, source, target):
        for key in source:
            if key not in target:
                target[key] = source[key].copy()

            elif key in (
                GSTR1_SubCategory.HSN.value,
                GSTR1_SubCategory.HSN_B2B.value,
                GSTR1_SubCategory.HSN_B2C.value,
            ):
                self._accumulate_data(source[key], target[key])

            elif key in (GSTR1_SubCategory.NIL_EXEMPT.value,):
                source = source[key]
                _target = target[key]

                for sub_key in source:
                    if sub_key not in _target:
                        _target[sub_key] = source[sub_key].copy()
                        continue

                    _target[sub_key].extend(source[sub_key])

            else:
                target[key].update(source[key])

    AMOUNT_FIELDS = (
        "total_taxable_value",
        "total_cess_amount",
        "total_igst_amount",
        "total_cgst_amount",
        "total_sgst_amount",
        "document_value",
    )

    def _accumulate_data(self, source, target):
        for key in source:
            if key not in target:
                target[key] = source[key].copy()
                continue

            for field in self.AMOUNT_FIELDS:
                target[key][field] += source[key].get(field)
