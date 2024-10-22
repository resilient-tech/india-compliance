# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

from datetime import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Date, Sum
from frappe.utils import cint, get_last_day, getdate

from india_compliance.gst_india.api_classes.taxpayer_base import (
    TaxpayerBaseAPI,
    otp_handler,
)
from india_compliance.gst_india.utils import get_gst_accounts_by_type
from india_compliance.gst_india.utils.gstin_info import get_gstr_1_return_status


class GSTR1Beta(Document):

    @frappe.whitelist()
    def recompute_books(self):
        return self.generate_gstr1(recompute_books=True)

    @frappe.whitelist()
    def sync_with_gstn(self, sync_for):
        return self.generate_gstr1(sync_for=sync_for, recompute_books=True)

    @frappe.whitelist()
    def mark_as_filed(self):
        period = get_period(self.month_or_quarter, self.year)
        return_status = get_gstr_1_return_status(
            self.company, self.company_gstin, period
        )

        if return_status != "Filed":
            frappe.msgprint(
                _("GSTR-1 is not yet filed on the GST Portal"), indicator="red"
            )

        else:
            frappe.db.set_value(
                "GST Return Log",
                f"GSTR1-{period}-{self.company_gstin}",
                "filing_status",
                return_status,
            )

        return self.generate_gstr1()

    @frappe.whitelist()
    @otp_handler
    def generate_gstr1(self, sync_for=None, recompute_books=False):
        period = get_period(self.month_or_quarter, self.year)

        # get gstr1 log
        if log_name := frappe.db.exists(
            "GST Return Log", f"GSTR1-{period}-{self.company_gstin}"
        ):

            gstr1_log = frappe.get_doc("GST Return Log", log_name)

            message = None
            if gstr1_log.status == "In Progress":
                message = (
                    "GSTR-1 is being prepared. Please wait for the process to complete."
                )

            elif gstr1_log.status == "Queued":
                message = (
                    "GSTR-1 download is queued and could take some time. Please wait"
                    " for the process to complete."
                )

            if message:
                frappe.msgprint(_(message), title=_("GSTR-1 Generation In Progress"))
                return

        else:
            gstr1_log = frappe.new_doc("GST Return Log")
            gstr1_log.company = self.company
            gstr1_log.gstin = self.company_gstin
            gstr1_log.return_period = period
            gstr1_log.return_type = "GSTR1"
            gstr1_log.is_quarterly = self.is_quarterly
            gstr1_log.insert()

        settings = frappe.get_cached_doc("GST Settings")

        if sync_for:
            gstr1_log.remove_json_for(sync_for)

        if recompute_books:
            gstr1_log.remove_json_for("books")

        # files are already present
        if gstr1_log.has_all_files(settings):
            data = gstr1_log.load_data()

            if data:
                data = data
                data["status"] = gstr1_log.filing_status or "Not Filed"
                gstr1_log.update_status("Generated")
                self.on_generate(data)
                return

        # validate auth token
        if gstr1_log.is_sek_needed(settings):
            TaxpayerBaseAPI(self.company_gstin).validate_auth_token()

        self.gstr1_log = gstr1_log

        # generate gstr1
        gstr1_log.update_status("In Progress")
        frappe.enqueue(self._generate_gstr1, queue="short")
        frappe.msgprint(_("GSTR-1 is being prepared"), alert=True)

    def _generate_gstr1(self):
        """
        Try to generate GSTR-1 data. Wrapper for generating GSTR-1 data
        """

        filters = frappe._dict(
            company=self.company,
            company_gstin=self.company_gstin,
            month_or_quarter=self.month_or_quarter,
            year=self.year,
            is_quarterly=self.is_quarterly,
        )

        try:
            self.gstr1_log.generate_gstr1_data(filters, callback=self.on_generate)

        except Exception as e:
            self.gstr1_log.update_status("Failed", commit=True)

            frappe.publish_realtime(
                "gstr1_generation_failed",
                message={"error": str(e), "filters": filters},
                user=frappe.session.user,
                doctype=self.doctype,
            )

            raise e

    def on_generate(self, data, filters=None):
        """
        Once data is generated, update the status and publish the data
        """
        if not filters:
            filters = self

        if getattr(self, "gstr1_log", None):
            self.gstr1_log.db_set(
                {"generation_status": "Generated", "is_latest_data": 1}
            )

        frappe.publish_realtime(
            "gstr1_data_prepared",
            message={"data": data, "filters": filters},
            user=frappe.session.user,
            doctype=self.doctype,
        )


####### DATA ######################################################################################


@frappe.whitelist()
def get_net_gst_liability(company, company_gstin, month_or_quarter, year, is_quarterly):
    """
    Returns the net output balance for the given return period as per ledger entries
    """

    frappe.has_permission("GSTR-1 Beta", throw=True)

    from_date, to_date = get_gstr_1_from_and_to_date(
        month_or_quarter, year, is_quarterly
    )

    filters = frappe._dict(
        {
            "company": company,
            "company_gstin": company_gstin,
            "from_date": from_date,
            "to_date": to_date,
        }
    )
    accounts = get_gst_accounts_by_type(company, "Output")

    gl_entry = frappe.qb.DocType("GL Entry")
    gst_ledger = frappe._dict(
        frappe.qb.from_(gl_entry)
        .select(gl_entry.account, (Sum(gl_entry.credit) - Sum(gl_entry.debit)))
        .where(gl_entry.account.isin(list(accounts.values())))
        .where(gl_entry.company == filters.company)
        .where(Date(gl_entry.posting_date) >= getdate(filters.from_date))
        .where(Date(gl_entry.posting_date) <= getdate(filters.to_date))
        .where(gl_entry.company_gstin == filters.company_gstin)
        .groupby(gl_entry.account)
        .run()
    )
    net_output_balance = {
        "total_igst_amount": gst_ledger.get(accounts["igst_account"], 0),
        "total_cgst_amount": gst_ledger.get(accounts["cgst_account"], 0),
        "total_sgst_amount": gst_ledger.get(accounts["sgst_account"], 0),
        "total_cess_amount": gst_ledger.get(accounts["cess_account"], 0)
        + gst_ledger.get(accounts["cess_non_advol_account"], 0),
    }

    return net_output_balance


####### UTILS ######################################################################################


def get_period(month_or_quarter: str, year: str) -> str:
    """
    Returns the period in the format MMYYYY
    as accepted by the GST Portal
    """

    if "-" in month_or_quarter:
        # Quarterly
        last_month = month_or_quarter.split("-")[1]
        month_number = str(getdate(f"{last_month}-{year}").month).zfill(2)

    else:
        # Monthly
        month_number = str(datetime.strptime(month_or_quarter, "%B").month).zfill(2)

    return f"{month_number}{year}"


def get_gstr_1_from_and_to_date(
    month_or_quarter: str, year: str, is_quarterly: str
) -> tuple:
    """
    Returns the from and to date for the given month or quarter and year
    This is used to filter the data for the given period in Books
    """
    if cint(is_quarterly):
        start_month, end_month = month_or_quarter.split("-")
        from_date = getdate(f"{year}-{start_month}-01")
        to_date = get_last_day(f"{year}-{end_month}-01")
    else:
        # Monthly (default)
        from_date = getdate(f"{year}-{month_or_quarter}-01")
        to_date = get_last_day(from_date)

    return from_date, to_date
