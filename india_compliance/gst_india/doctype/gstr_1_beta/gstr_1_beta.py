# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder import Case
from frappe.query_builder.functions import Date, IfNull, Sum
from frappe.utils import get_last_day, getdate

from india_compliance.gst_india.api_classes.taxpayer_base import (
    TaxpayerBaseAPI,
    otp_handler,
)
from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    verify_request_in_progress,
)
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    get_gst_return_log,
)
from india_compliance.gst_india.utils import (
    MONTHS,
    get_gst_accounts_by_type,
    get_period,
)
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
    def generate_gstr1(
        self, sync_for=None, recompute_books=False, only_books_data=None, message=None
    ):
        period = get_period(self.month_or_quarter, self.year)
        log_name = f"GSTR1-{period}-{self.company_gstin}"

        gstr1_log = get_gst_return_log(
            log_name, company=self.company, filing_preference=self.filing_preference
        )

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

        settings = frappe.get_cached_doc("GST Settings")

        # default
        if not self.get("filing_preference"):
            self.filing_preference = "Monthly"

        # updated after last generation
        if self.filing_preference != gstr1_log.filing_preference:
            recompute_books = True
            gstr1_log.db_set("filing_preference", self.filing_preference)

        if not gstr1_log.filing_preference:
            recompute_books = True

        if sync_for:
            gstr1_log.remove_json_for(sync_for)

        if recompute_books:
            gstr1_log.remove_json_for("books")

        # failed while downloading gov data
        if only_books_data:
            data = gstr1_log.load_data("books", "books_summary")
            data["status"] = gstr1_log.filing_status or "Not Filed"
            return data

        if gstr1_log.has_all_files(settings):
            data = gstr1_log.get_gstr1_data()

            if data:
                return data

        # validate auth token
        if gstr1_log.is_sek_needed(settings):
            TaxpayerBaseAPI(self.company_gstin).validate_auth_token()

        self.gstr1_log = gstr1_log

        # generate gstr1
        gstr1_log.update_status("In Progress")
        frappe.enqueue(self._generate_gstr1, queue="long")

        if not message:
            message = "GSTR-1 is being prepared"

        frappe.msgprint(_(message), alert=True)

    def _generate_gstr1(self):
        """
        Try to generate GSTR-1 data. Wrapper for generating GSTR-1 data
        """

        filters = frappe._dict(
            company=self.company,
            company_gstin=self.company_gstin,
            month_or_quarter=self.month_or_quarter,
            year=self.year,
            filing_preference=self.filing_preference,
        )

        try:
            self.gstr1_log.generate_gstr1_data(filters, callback=self.on_generate)

        except Exception as e:
            self.gstr1_log.update_status("Failed", commit=True)

            frappe.publish_realtime(
                "gstr1_generation_failed",
                message={"error": str(e), "filters": filters},
                user=frappe.session.user,
            )

            raise e

    def on_generate(self, filters=None, error_log=None):
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
            message={"filters": filters, "error_log": error_log},
            user=frappe.session.user,
        )


@frappe.whitelist()
@otp_handler
def perform_gstr1_action(action, month_or_quarter, year, company_gstin, **kwargs):
    frappe.has_permission("GST Return Log", "write", throw=True)

    gstr_1_log = frappe.get_doc(
        "GST Return Log",
        f"GSTR1-{get_period(month_or_quarter, year)}-{company_gstin}",
    )
    del kwargs["cmd"]

    if action == "upload_gstr1":
        from india_compliance.gst_india.doctype.gstr_1_beta.gstr_1_export import (
            get_gstr_1_json,
        )

        data = get_gstr_1_json(
            company_gstin,
            year,
            month_or_quarter,
            delete_missing=True,
        )
        kwargs["json_data"] = data.get("data")

    return getattr(gstr_1_log, action)(**kwargs)


@frappe.whitelist()
@otp_handler
def check_action_status(month_or_quarter, year, company_gstin, action):
    frappe.has_permission("GST Return Log", "write", throw=True)

    gstr_1_log = frappe.get_doc(
        "GST Return Log",
        f"GSTR1-{get_period(month_or_quarter, year)}-{company_gstin}",
    )

    method_name = f"process_{action}_gstr1"
    data = getattr(gstr_1_log, method_name)()

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
def mark_as_unfiled(filters, force):
    frappe.has_permission("GST Return Log", "write", throw=True)

    filters = frappe._dict(json.loads(filters))
    log_name = f"GSTR1-{get_period(filters.month_or_quarter, filters.year)}-{filters.company_gstin}"

    force = bool(force)
    if force:
        return_log = frappe.get_doc("GST Return Log", log_name)
        verify_request_in_progress(return_log, force)

    frappe.db.set_value("GST Return Log", log_name, "filing_status", "Not Filed")


@frappe.whitelist()
def get_journal_entries(month_or_quarter, year, company, filing_preference):
    if not frappe.has_permission("Journal Entry", "create"):
        return

    from_date, to_date = get_gstr_1_from_and_to_date(
        month_or_quarter, year, filing_preference
    )

    gst_accounts = list(
        get_gst_accounts_by_type(company, "Sales Reverse Charge", throw=False).values()
    )

    if not gst_accounts:
        return

    sales_invoice = frappe.qb.DocType("Sales Invoice")
    sales_invoice_taxes = frappe.qb.DocType("Sales Taxes and Charges")

    data = (
        frappe.qb.from_(sales_invoice)
        .join(sales_invoice_taxes)
        .on(sales_invoice.name == sales_invoice_taxes.parent)
        .select(
            sales_invoice_taxes.account_head.as_("account"),
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
        .where(sales_invoice.docstatus == 1)
        .groupby(sales_invoice_taxes.account_head)
        .run(as_dict=True)
    )

    if not data:
        return

    return {"data": data, "posting_date": to_date}


@frappe.whitelist()
def get_gst_and_round_off_accounts(month_or_quarter, year, company, filing_preference):
    """
    Get GST output accounts and round off account for journal entry creation.

    Returns:
        dict: Contains account details and posting date, or None if accounts not found
    """
    if not frappe.has_permission("Journal Entry", "create"):
        return

    _, to_date = get_gstr_1_from_and_to_date(month_or_quarter, year, filing_preference)

    # Get Output GST accounts using existing utility
    try:
        gst_accounts = get_gst_accounts_by_type(company, "Output")

    except Exception:
        return

    if not gst_accounts:
        return

    # For Round Off Account
    round_off_account = frappe.get_all(
        "Account",
        filters={
            "company": company,
            "account_type": "Round Off",
        },
        pluck="name",
    )

    if not round_off_account:
        return

    round_off_account = round_off_account[0]

    account = {
        "igst_account": gst_accounts.get("igst_account"),
        "cgst_account": gst_accounts.get("cgst_account"),
        "sgst_account": gst_accounts.get("sgst_account"),
        "cess_account": gst_accounts.get("cess_account"),
        "cess_non_advol_account": gst_accounts.get("cess_non_advol_account"),
        "round_off_account": round_off_account,
    }

    return {
        "account": account,
        "posting_date": to_date,
    }


@frappe.whitelist()
def make_journal_entry(
    company, company_gstin, month_or_quarter, year, accounts, values
):
    if not frappe.has_permission("Journal Entry", "create"):
        return

    if isinstance(values, str):
        values = frappe.parse_json(values)

    if isinstance(accounts, str):
        accounts = frappe.parse_json(accounts)

    journal_entry = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "company": company,
            "company_gstin": company_gstin,
            "posting_date": values.posting_date,
            "user_remark": f"Reduced Output GST Liability to the extent of Sales Reverse Charge as per GSTR-1 for {month_or_quarter} - {year}",
            "accounts": accounts,
        }
    )
    journal_entry.save()

    if values.auto_submit == 1:
        journal_entry.submit()

    return journal_entry.name


####### DATA ######################################################################################


@frappe.whitelist()
def get_net_gst_liability(
    company, company_gstin, month_or_quarter, year, filing_preference=None
):
    """
    Returns the net output balance for the given return period as per ledger entries
    """

    frappe.has_permission("GSTR-1 Beta", throw=True)

    from_date, to_date = get_gstr_1_from_and_to_date(
        month_or_quarter, year, filing_preference
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


def get_gstr_1_from_and_to_date(
    month_or_quarter: str, year: str, filing_preference: str
) -> tuple:
    """
    Returns the from and to date for the given month or quarter and year
    This is used to filter the data for the given period in Books
    """
    start_month = end_month = MONTHS.index(month_or_quarter) + 1

    # only for quarter ending month
    if filing_preference == "Quarterly" and start_month % 3 == 0:
        start_month -= 2

    from_date = getdate(f"{year}-{start_month}-01")
    to_date = get_last_day(f"{year}-{end_month}-01")

    return from_date, to_date


@frappe.whitelist()
def get_filing_preference_from_log(month_or_quarter: str, year: str, company_gstin):
    period = get_period(month_or_quarter, year)
    filing_preference = frappe.db.get_value(
        "GST Return Log", f"GSTR1-{period}-{company_gstin}", "filing_preference"
    )

    if not filing_preference:
        return None

    return filing_preference
