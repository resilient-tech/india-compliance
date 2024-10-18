# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import json
from datetime import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder import Case
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import Date, IfNull, Sum
from frappe.utils import get_last_day, getdate

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
    def generate_gstr1(self, sync_for=None, recompute_books=False, display_alert=True):
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
                if error_data := gstr1_log.get_json_for("upload_error"):
                    data["error"] = error_data
                gstr1_log.update_status("Generated")
                return data

        # validate auth token
        if gstr1_log.is_sek_needed(settings):
            TaxpayerBaseAPI(self.company_gstin).validate_auth_token()

        self.gstr1_log = gstr1_log

        # generate gstr1
        gstr1_log.update_status("In Progress")
        frappe.enqueue(self._generate_gstr1, queue="short")
        if display_alert:
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

    def on_generate(self, filters=None):
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
            message={"filters": filters},
            user=frappe.session.user,
            doctype=self.doctype,
        )


@frappe.whitelist()
@otp_handler
def handle_gstr1_action(action, month_or_quarter, year, company_gstin, **kwargs):
    frappe.has_permission("GSTR-1 Beta", "write", throw=True)

    gstr_1_log = frappe.get_doc(
        "GST Return Log",
        f"GSTR1-{get_period(month_or_quarter, year)}-{company_gstin}",
    )
    del kwargs["cmd"]

    if action == "upload_gstr1":
        from india_compliance.gst_india.doctype.gstr_1_beta.gstr_1_export import (
            download_gstr_1_json,
        )

        data = download_gstr_1_json(
            company_gstin,
            year,
            month_or_quarter,
            delete_missing=True,
        )
        kwargs["json_data"] = data.get("data")

    return getattr(gstr_1_log, action)(**kwargs)


@frappe.whitelist()
@otp_handler
def process_gstr1_request(month_or_quarter, year, company_gstin, action):
    gstr_1_log = frappe.get_doc(
        "GST Return Log",
        f"GSTR1-{get_period(month_or_quarter, year)}-{company_gstin}",
    )

    method_name = f"process_{action}_gstr1"
    method = getattr(gstr_1_log, method_name)
    data = method()

    if not data:
        data = {}

    data.update(
        {
            "month_or_quarter": month_or_quarter,
            "year": year,
            "company_gstin": company_gstin,
        }
    )
    return data


@frappe.whitelist()
def update_filing_status(filters):
    frappe.has_permission("GST Return Log", "write", throw=True)

    filters = frappe._dict(json.loads(filters))
    log_name = f"GSTR1-{get_period(filters.month_or_quarter, filters.year)}-{filters.company_gstin}"

    frappe.db.set_value("GST Return Log", log_name, "filing_status", "Not Filed")


@frappe.whitelist()
def get_journal_entries(month_or_quarter, year, company):
    frappe.has_permission("Journal Entry", "read", throw=True)

    from_date, to_date = get_gstr_1_from_and_to_date(month_or_quarter, year)

    journal_entry = frappe.qb.DocType("Journal Entry")
    journal_entry_account = frappe.qb.DocType("Journal Entry Account")

    gst_accounts = list(
        get_gst_accounts_by_type(company, "Sales Reverse Charge", throw=False).values()
    )

    if not gst_accounts:
        return True

    return bool(
        frappe.qb.from_(journal_entry)
        .join(journal_entry_account)
        .on(journal_entry.name == journal_entry_account.parent)
        .select(
            journal_entry.name,
        )
        .where(journal_entry.posting_date.between(getdate(from_date), getdate(to_date)))
        .where(journal_entry_account.account.isin(gst_accounts))
        .where(journal_entry.docstatus == 1)
        .run()
    )


@frappe.whitelist()
def make_journal_entry(company, company_gstin, month_or_quarter, year, auto_submit):
    frappe.has_permission("Journal Entry", "write", throw=True)

    from_date, to_date = get_gstr_1_from_and_to_date(month_or_quarter, year)
    sales_invoice = frappe.qb.DocType("Sales Invoice")
    sales_invoice_taxes = frappe.qb.DocType("Sales Taxes and Charges")

    data = (
        frappe.qb.from_(sales_invoice)
        .join(sales_invoice_taxes)
        .on(sales_invoice.name == sales_invoice_taxes.parent)
        .select(
            sales_invoice_taxes.account_head.as_("account"),
            ConstantColumn("Sales Invoice").as_("reference_type"),
            Case()
            .when(
                sales_invoice_taxes.tax_amount > 0, Sum(sales_invoice_taxes.tax_amount)
            )
            .as_("debit_in_account_currency"),
            Case()
            .when(
                sales_invoice_taxes.tax_amount < 0,
                Sum(sales_invoice_taxes.tax_amount * (-1)),
            )
            .as_("credit_in_account_currency"),
        )
        .where(sales_invoice.is_reverse_charge == 1)
        .where(
            Date(sales_invoice.posting_date).between(
                getdate(from_date), getdate(to_date)
            )
        )
        .where(IfNull(sales_invoice_taxes.gst_tax_type, "") != "")
        .groupby(sales_invoice_taxes.account_head)
        .run(as_dict=True)
    )

    journal_entry = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "company": company,
            "company_gstin": company_gstin,
            "posting_date": get_last_day(to_date),
        }
    )
    journal_entry.extend("accounts", data)
    journal_entry.save()

    if auto_submit == "1":
        journal_entry.submit()

    return journal_entry.name


####### DATA ######################################################################################


@frappe.whitelist()
def get_net_gst_liability(company, company_gstin, month_or_quarter, year):
    """
    Returns the net output balance for the given return period as per ledger entries
    """

    frappe.has_permission("GSTR-1 Beta", throw=True)

    from_date, to_date = get_gstr_1_from_and_to_date(month_or_quarter, year)

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


def get_gstr_1_from_and_to_date(month_or_quarter: str, year: str) -> tuple:
    """
    Returns the from and to date for the given month or quarter and year
    This is used to filter the data for the given period in Books
    """

    filing_frequency = frappe.get_cached_value("GST Settings", None, "filing_frequency")

    if filing_frequency == "Quarterly":
        start_month, end_month = month_or_quarter.split("-")
        from_date = getdate(f"{year}-{start_month}-01")
        to_date = get_last_day(f"{year}-{end_month}-01")
    else:
        # Monthly (default)
        from_date = getdate(f"{year}-{month_or_quarter}-01")
        to_date = get_last_day(from_date)

    return from_date, to_date
