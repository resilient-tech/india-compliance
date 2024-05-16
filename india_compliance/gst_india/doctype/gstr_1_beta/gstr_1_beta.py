# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

from datetime import datetime

import frappe
from frappe import _, unscrub
from frappe.desk.form.load import run_onload
from frappe.model.document import Document
from frappe.query_builder.functions import Date, Sum
from frappe.utils import flt, get_last_day, getdate

from india_compliance.gst_india.utils import get_gst_accounts_by_type
from india_compliance.gst_india.utils.gstin_info import get_gstr_1_return_status
from india_compliance.gst_india.utils.gstr_1 import GSTR1_SubCategories
from india_compliance.gst_india.utils.gstr_1.gstr_1_download import (
    download_gstr1_json_data,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import (
    GSTR1BooksData,
    summarize_retsum_data,
)
from india_compliance.gst_india.utils.gstr_utils import request_otp


class GSTR1Beta(Document):

    def onload(self):
        data = getattr(self, "data", None)
        if data is not None:
            self.set_onload("data", data)

    @frappe.whitelist()
    def recompute_books(self):
        self.validate(recompute_books=True)

    @frappe.whitelist()
    def sync_with_gstn(self, sync_for):
        self.validate(sync_for=sync_for)

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
                "GSTR-1 Filed Log",
                f"{period}-{self.company_gstin}",
                "filing_status",
                return_status,
            )

        self.validate()
        run_onload(self)

    def validate(self, sync_for=None, recompute_books=False):
        period = get_period(self.month_or_quarter, self.year)

        # get gstr1 log
        if log_name := frappe.db.exists(
            "GSTR-1 Filed Log", f"{period}-{self.company_gstin}"
        ):

            gstr1_log = frappe.get_doc("GSTR-1 Filed Log", log_name)

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
            gstr1_log = frappe.new_doc("GSTR-1 Filed Log")
            gstr1_log.company = self.company
            gstr1_log.gstin = self.company_gstin
            gstr1_log.return_period = period
            gstr1_log.insert()

        settings = frappe.get_cached_doc("GST Settings")

        if sync_for:
            gstr1_log.remove_json_for(sync_for)

        if recompute_books:
            gstr1_log.remove_json_for("books")

        # files are already present
        if gstr1_log.has_all_files(settings):
            self.data = gstr1_log.load_data()
            self.data["status"] = gstr1_log.filing_status or "Not Filed"
            gstr1_log.update_status("Generated")
            return

        # request OTP
        if gstr1_log.is_sek_needed(settings) and not gstr1_log.is_sek_valid(settings):
            request_otp(self.company_gstin)
            self.data = "otp_requested"
            return

        self.gstr1_log = gstr1_log

        # generate gstr1
        gstr1_log.update_status("In Progress")
        frappe.enqueue(self.generate_gstr1, queue="short")
        frappe.msgprint("GSTR-1 is being prepared", alert=True)

    def generate_gstr1(self):
        filters = {
            "company_gstin": self.company_gstin,
            "month_or_quarter": self.month_or_quarter,
            "year": self.year,
        }

        try:
            self._generate_gstr1_data(filters)

        except Exception as e:
            self.gstr1_log.update_status("Failed", commit=True)

            frappe.publish_realtime(
                "gstr1_generation_failed",
                message={"error": str(e), "filters": filters},
                user=frappe.session.user,
                doctype=self.doctype,
            )

            raise e

    def _generate_gstr1_data(self, filters):
        data = {}

        def on_generate():
            self.gstr1_log.db_set(
                {"generation_status": "Generated", "is_latest_data": 1}
            )

            frappe.publish_realtime(
                "gstr1_data_prepared",
                message={"data": data, "filters": filters},
                user=frappe.session.user,
                doctype=self.doctype,
            )

        def summarize_data(gov_data_field=None):
            summary_fields = {
                "reconcile": "reconcile_summary",
                f"{gov_data_field}": f"{gov_data_field}_summary",
                "books": "books_summary",
            }

            for key, field in summary_fields.items():
                if not data.get(key):
                    continue

                if self.gstr1_log.is_latest_data and self.gstr1_log.get(field):
                    data[field] = self.gstr1_log.get_json_for(field)
                    continue

                if key == "filed":
                    summary_data = summarize_retsum_data(data[key].get("summary"))
                else:
                    summary_data = self.gstr1_log.summarize_data(data[key])

                self.gstr1_log.update_json_for(field, summary_data)
                data[field] = summary_data

        # APIs Disabled
        if not self.gstr1_log.is_gstr1_api_enabled():
            books_data = get_books_gstr1_data(self)

            data["status"] = "Not Filed"
            data["books"] = self.gstr1_log.normalize_data(books_data)

            summarize_data()
            on_generate()
            return

        # APIs Enabled
        status = self.gstr1_log.filing_status
        if not status:
            status = get_gstr_1_return_status(
                self.gstr1_log.company,
                self.gstr1_log.gstin,
                self.gstr1_log.return_period,
            )
            self.gstr1_log.filing_status = status

        if status == "Filed":
            gov_data_field = "filed"
        else:
            gov_data_field = "unfiled"

        # Get Data
        gov_data, is_enqueued = get_gov_gstr1_data(self.gstr1_log)

        if error_type := gov_data.get("error_type"):
            # otp_requested, invalid_otp

            if error_type == "invalid_otp":
                request_otp(self.company_gstin)

            data = "otp_requested"
            on_generate()
            return

        books_data = get_books_gstr1_data(self)

        if is_enqueued:
            return

        reconcile_data = get_reconcile_gstr1_data(self.gstr1_log, gov_data, books_data)

        # Compile Data
        data["status"] = status

        data["reconcile"] = self.gstr1_log.normalize_data(reconcile_data)
        data[gov_data_field] = self.gstr1_log.normalize_data(gov_data)
        data["books"] = self.gstr1_log.normalize_data(books_data)

        summarize_data(gov_data_field)
        on_generate()


####### DATA ######################################################################################


def get_gov_gstr1_data(gstr1_log):
    if gstr1_log.filing_status == "Filed":
        data_field = "filed"

    else:
        data_field = "unfiled"

    # data exists
    if gstr1_log.get(data_field):
        mapped_data = gstr1_log.get_json_for(data_field)
        if mapped_data:
            return mapped_data, False

    # download data
    return download_gstr1_json_data(gstr1_log)


def get_books_gstr1_data(filters):
    # Query / Process / Map / Sumarize / Optionally Save & Return
    data_field = "books"
    gstr1_log = filters.gstr1_log

    # data exists
    if gstr1_log.is_latest_data and gstr1_log.get(data_field):
        mapped_data = gstr1_log.get_json_for(data_field)

        if mapped_data:
            return mapped_data

    from_date, to_date = get_from_and_to_date(filters.month_or_quarter, filters.year)

    _filters = frappe._dict(
        {
            "company": filters.company,
            "company_gstin": filters.company_gstin,
            "from_date": from_date,
            "to_date": to_date,
        }
    )

    # compute data
    mapped_data = GSTR1BooksData(_filters).prepare_mapped_data()

    gstr1_log.update_json_for(data_field, mapped_data)

    return mapped_data


def get_reconcile_gstr1_data(gstr1_log, gov_data, books_data):
    # Everything from gov_data compared with books_data
    # Missing in gov_data
    # Update books data (optionally if not filed)
    # Prepare data / Sumarize / Save & Return / Optionally save books data
    if gstr1_log.is_latest_data and gstr1_log.reconcile:
        return gstr1_log.get_json_for("reconcile")

    reconciled_data = {}
    if gstr1_log.filing_status == "Filed":
        update_books_match = False
    else:
        update_books_match = True

    for subcategory in GSTR1_SubCategories:
        subcategory = subcategory.value
        books_subdata = books_data.get(subcategory) or {}
        gov_subdata = gov_data.get(subcategory) or {}

        if not books_subdata and not gov_subdata:
            continue

        ignore_upload_status = subcategory in [
            GSTR1_SubCategories.HSN.value,
            GSTR1_SubCategories.DOC_ISSUE.value,
        ]
        is_list = False  # Object Type for the subdata_value

        reconcile_subdata = {}

        # Books vs Gov
        for key, books_value in books_subdata.items():
            if not reconcile_subdata:
                is_list = isinstance(books_value, list)

            gov_value = gov_subdata.get(key)
            reconcile_row = get_reconciled_row(books_value, gov_value)

            if reconcile_row:
                reconcile_subdata[key] = reconcile_row

            if not update_books_match or ignore_upload_status:
                continue

            books_value = books_value[0] if is_list else books_value

            if books_value.get("upload_status"):
                update_books_match = False

            # Update Books Data
            if not gov_value:
                books_value["upload_status"] = "Not Uploaded"

            if reconcile_row:
                books_value["upload_status"] = "Mismatch"
            else:
                books_value["upload_status"] = "Uploaded"

        # In Gov but not in Books
        for key, gov_value in gov_subdata.items():
            if key in books_subdata:
                continue

            if not reconcile_subdata:
                is_list = isinstance(gov_value, list)

            reconcile_subdata[key] = get_reconciled_row(None, gov_value)

            if not update_books_match or ignore_upload_status:
                continue

            books_empty_row = get_empty_row(gov_value[0] if is_list else gov_value)
            books_empty_row["upload_status"] = "Missing in Books"

            books_subdata[key] = [books_empty_row] if is_list else books_empty_row

        if update_books_match and not books_data.get(subcategory):
            books_data[subcategory] = books_subdata

        if reconcile_subdata:
            reconciled_data[subcategory] = reconcile_subdata

    if update_books_match:
        gstr1_log.update_json_for("books", books_data)

    gstr1_log.update_json_for("reconcile", reconciled_data)

    return reconciled_data


def get_reconciled_row(books_row, gov_row):
    """
    Compare books_row with gov_row and return the difference

    Args:
        books_row (dict|list): Books Row Data
        gov_row (dict|list): Gov Row Data

    Returns:
        dict|list: Reconciled Row Data

    Steps:
        1. Get Empty Row with all values as 0
        2. Prefer Gov Row if available to compute empty row
        3. Compute comparable Gov and Books Row
        4. Compare the rows
        5. Compute match status and differences
        6. Return the reconciled row only if there are differences
    """
    is_list = isinstance(gov_row if gov_row else books_row, list)

    # Get Empty Row
    if is_list:
        reconcile_row = get_empty_row(gov_row[0] if gov_row else books_row[0])
        gov_row = gov_row[0] if gov_row else {}
        books_row = get_aggregated_row(books_row) if books_row else {}

    else:
        reconcile_row = get_empty_row(gov_row or books_row)
        gov_row = gov_row or {}
        books_row = books_row or {}

    # Default Status
    reconcile_row["match_status"] = "Matched"
    reconcile_row["differences"] = []

    if not gov_row:
        reconcile_row["match_status"] = "Missing in GSTR-1"

    if not books_row:
        reconcile_row["match_status"] = "Missing in Books"

    # Compute Differences
    for key, value in reconcile_row.items():
        if isinstance(value, (int, float)) and key not in ("tax_rate"):
            reconcile_row[key] = flt(
                (books_row.get(key) or 0) - (gov_row.get(key) or 0), 2
            )
            has_different_value = reconcile_row[key] != 0

        elif key in ("customer_gstin", "place_of_supply"):
            has_different_value = books_row.get(key) != gov_row.get(key)

        else:
            continue

        if not has_different_value:
            continue

        if "Missing" not in reconcile_row["match_status"]:
            reconcile_row["match_status"] = "Mismatch"
            reconcile_row["differences"].append(unscrub(key))

    # Return
    if reconcile_row["match_status"] == "Matched":
        return

    reconcile_row["books"] = books_row
    reconcile_row["gov"] = gov_row

    if is_list:
        return [reconcile_row]

    return reconcile_row


@frappe.whitelist()
def get_output_gst_balance(company, company_gstin, month_or_quarter, year):
    """
    Returns the net output balance for the given return period
    """

    frappe.has_permission("GSTR-1 Beta", throw=True)

    from_date, to_date = get_from_and_to_date(month_or_quarter, year)

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


def get_from_and_to_date(month_or_quarter: str, year: str) -> tuple:
    """
    Returns the from and to date for the given month or quarter and year
    This is used to filter the data for the given period in Books
    """

    filing_frequency = get_gstr1_filing_frequency()

    if filing_frequency == "Monthly":
        from_date = getdate(f"{year}-{month_or_quarter}-01")
        to_date = get_last_day(from_date)
    else:
        start_month, end_month = month_or_quarter.split("-")
        from_date = getdate(f"{year}-{start_month}-01")
        to_date = get_last_day(f"{year}-{end_month}-01")

    return from_date, to_date


def get_gstr1_filing_frequency():
    gst_settings = frappe.get_cached_doc("GST Settings")
    return gst_settings.filing_frequency


def get_empty_row(row: dict):
    """
    Row with all values as 0
    """
    empty_row = row.copy()

    for key, value in empty_row.items():
        if isinstance(value, (int, float)):
            empty_row[key] = 0

    return empty_row


def get_aggregated_row(books_rows: list) -> dict:
    """
    There can be multiple rows in books data for a single row in gov data
    Aggregate all the rows to a single row
    """
    aggregated_row = {}

    for row in books_rows:
        if not aggregated_row:
            aggregated_row = row.copy()
            continue

        for key, value in row.items():
            if isinstance(value, (int, float)):
                aggregated_row[key] += value

    return aggregated_row
