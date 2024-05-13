# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import json
from datetime import datetime

import frappe
from frappe import _, unscrub
from frappe.desk.form.load import run_onload
from frappe.model.document import Document
from frappe.query_builder.functions import Date, Sum
from frappe.utils import flt, get_last_day, getdate

from india_compliance.gst_india.doctype.gstr_1_filed_log.gstr_1_filed_log import (
    summarize_data,
)
from india_compliance.gst_india.report.gstr_1.gstr_1 import (
    GSTR1DocumentIssuedSummary,
    GSTR11A11BData,
)
from india_compliance.gst_india.utils.__init__ import get_gst_accounts_by_type
from india_compliance.gst_india.utils.exporter import ExcelExporter
from india_compliance.gst_india.utils.gstin_info import get_gstr_1_return_status
from india_compliance.gst_india.utils.gstr_1 import (
    INVOICE_SUB_CATEGORIES,
    GSTR1_Categories,
    GSTR1_DataFields,
    GSTR1_Excel_Categories,
    GSTR1_ItemFields,
    GSTR1_SubCategories,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_data import GSTR1Invoices
from india_compliance.gst_india.utils.gstr_1.gstr_1_download import (
    download_gstr1_json_data,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import (
    convert_to_gov_data_format,
    summarize_retsum_data,
)
from india_compliance.gst_india.utils.gstr_utils import request_otp

COLOR_PALLATE = frappe._dict(
    {
        "dark_gray": "d9d9d9",
        "light_gray": "f2f2f2",
        "dark_pink": "e6b9b8",
        "light_pink": "f2dcdb",
        "sky_blue": "c6d9f1",
        "light_blue": "dce6f2",
        "green": "d7e4bd",
        "light_green": "ebf1de",
    }
)

AMOUNT_FIELDS = {
    GSTR1_DataFields.TAXABLE_VALUE.value: 0,
    GSTR1_DataFields.IGST.value: 0,
    GSTR1_DataFields.CGST.value: 0,
    GSTR1_DataFields.SGST.value: 0,
    GSTR1_DataFields.CESS.value: 0,
}


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
        self.settings = settings

        # generate gstr1
        gstr1_log.update_status("In Progress")
        frappe.enqueue(self.generate_gstr1, queue="short", now=True)
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

        def _summarize_data(gov_data_field=None):
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
                    summary_data = summarize_data(data[key])

                self.gstr1_log.update_json_for(field, summary_data)
                data[field] = summary_data

        # APIs Disabled
        if not self.settings.analyze_filed_data:
            books_data = compute_books_gstr1_data(self)

            data["status"] = "Not Filed"
            data["books"] = self.gstr1_log.normalize_data(books_data)

            _summarize_data()
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
        gov_data, is_enqueued = get_gstr1_json_data(self.gstr1_log)

        if error_type := gov_data.get("error_type"):
            # otp_requested, invalid_otp

            if error_type == "invalid_otp":
                request_otp(self.company_gstin)

            data = "otp_requested"
            on_generate()
            return

        books_data = compute_books_gstr1_data(self)

        if is_enqueued:
            return

        reconcile_data = reconcile_gstr1_data(self.gstr1_log, gov_data, books_data)

        # Compile Data
        data["status"] = status

        data["reconcile"] = self.gstr1_log.normalize_data(reconcile_data)
        data[gov_data_field] = self.gstr1_log.normalize_data(gov_data)
        data["books"] = self.gstr1_log.normalize_data(books_data)

        _summarize_data(gov_data_field)
        on_generate()


def get_period(month_or_quarter, year):
    if "-" in month_or_quarter:
        # Quarterly
        last_month = month_or_quarter.split("-")[1]
        month_number = str(getdate(f"{last_month}-{year}").month).zfill(2)

    else:
        # Monthly
        month_number = str(datetime.strptime(month_or_quarter, "%B").month).zfill(2)

    return f"{month_number}{year}"


def generate_gstr1():
    pass


def get_gstr1_json_data(gstr1_log):
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


def compute_books_gstr1_data(filters, save=False, periodicity="Monthly"):
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
    mapped_data = GSTR1MappedData(_filters).prepare_mapped_data()

    gstr1_log.update_json_for(data_field, mapped_data)

    return mapped_data


def get_from_and_to_date(month_or_quarter, year):
    filing_frequency = get_gstr1_filing_frequency()

    if filing_frequency == "Monthly":
        from_date = getdate(f"{year}-{month_or_quarter}-01")
        to_date = get_last_day(from_date)
    else:
        start_month, end_month = month_or_quarter.split("-")
        from_date = getdate(f"{year}-{start_month}-01")
        to_date = get_last_day(f"{year}-{end_month}-01")

    return from_date, to_date


def reconcile_gstr1_data(gstr1_log, gov_data, books_data):
    # Everything from gov_data compared with books_data
    # Missing in gov_data
    # Update books data (optionally if not filed)
    # Prepare data / Sumarize / Save & Return / Optionally save books data
    if gstr1_log.is_latest_data and gstr1_log.reconcile:
        return gstr1_log.get_json_for("reconcile")

    reconciled_data = {}
    if gstr1_log.filing_status == "Filed":
        update_books_match = False
        reconcile_only_invoices = False
    else:
        update_books_match = True
        reconcile_only_invoices = True

    for subcategory in GSTR1_SubCategories:
        subcategory = subcategory.value
        books_subdata = books_data.get(subcategory) or {}
        gov_subdata = gov_data.get(subcategory) or {}

        if not books_subdata and not gov_subdata:
            continue

        is_invoice_subcategory = subcategory in INVOICE_SUB_CATEGORIES

        if reconcile_only_invoices and not is_invoice_subcategory:
            continue

        reconcile_subdata = {}

        # Books vs Gov
        for key, books_value in books_subdata.items():
            gov_value = gov_subdata.get(key)
            reconcile_row = get_reconciled_row(books_value, gov_value)

            if reconcile_row:
                reconcile_subdata[key] = reconcile_row

            if not update_books_match or not is_invoice_subcategory:
                continue

            if books_subdata[key].get("upload_status"):
                update_books_match = False

            # Update Books Data
            if not gov_value:
                books_subdata[key]["upload_status"] = "Not Uploaded"

            if reconcile_row:
                books_subdata[key]["upload_status"] = "Mismatch"
            else:
                books_subdata[key]["upload_status"] = "Uploaded"

        # In Gov but not in Books
        for key, gov_value in gov_subdata.items():
            if key in books_subdata:
                continue

            reconcile_subdata[key] = get_reconciled_row(None, gov_value)

            if not update_books_match or not is_invoice_subcategory:
                continue

            is_list = isinstance(gov_value, list)
            books_subdata[key] = get_empty_row(gov_value[0] if is_list else gov_value)
            books_subdata[key]["upload_status"] = "Missing in Books"

        if update_books_match and not books_data.get(subcategory):
            books_data[subcategory] = books_subdata

        if reconcile_subdata:
            reconciled_data[subcategory] = reconcile_subdata

        # 2 types of data to be downloaded (for JSON only)
        # 1. Difference to be uploaded
        #   - Upload all except uploaded. Missing in Books will come with zero values
        # 2. All as per Books
        #  - Upload all except missing in Books

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


def get_empty_row(row: dict):
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


###################
def get_gstr1_filing_frequency():
    gst_settings = frappe.get_cached_doc("GST Settings")
    return gst_settings.filing_frequency


@frappe.whitelist()
def is_latest_data(company_gstin, month_or_quarter, year):
    period = get_period(month_or_quarter, year)
    if log_name := frappe.db.exists("GSTR-1 Filed Log", f"{period}-{company_gstin}"):
        gstr1_log = frappe.get_doc("GSTR-1 Filed Log", log_name)
        return gstr1_log.is_latest_data

    return True


@frappe.whitelist()
def get_output_gst_balance(company, company_gstin, month_or_quarter, year):
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


####################################################################################################
####### DOWNLOAD APIs ##############################################################################
####################################################################################################


@frappe.whitelist()
def download_books_as_excel(company_gstin, month_or_quarter, year):

    books_excel = BooksExcel(company_gstin, month_or_quarter, year)
    books_excel.export_data()

    return "Data Downloaded to Excel Successfully"


@frappe.whitelist()
def download_reconcile_as_excel(company_gstin, month_or_quarter, year):

    reconcile_excel = ReconcileExcel(company_gstin, month_or_quarter, year)
    reconcile_excel.export_data()

    return "Data Downloaded to Excel Successfully"


@frappe.whitelist()
def download_gstr_1_json(
    company_gstin,
    year,
    month_or_quarter,
    include_uploaded=False,
    overwrite_missing=False,
):
    if isinstance(include_uploaded, str):
        include_uploaded = json.loads(include_uploaded)

    if isinstance(overwrite_missing, str):
        overwrite_missing = json.loads(overwrite_missing)

    period = get_period(month_or_quarter, year)
    gstr1_log = frappe.get_doc("GSTR-1 Filed Log", f"{period}-{company_gstin}")

    data = gstr1_log.get_json_for("books")

    for subcategory, subcategory_data in data.items():
        discard_invoices = []

        if isinstance(subcategory_data, str):
            continue

        for key, row in subcategory_data.items():
            if not row.get("upload_status"):
                continue

            if row.get("upload_status") == "Uploaded" and not include_uploaded:
                discard_invoices.append(key)

            if row.get("upload_status") == "Missing in Books" and not overwrite_missing:
                discard_invoices.append(key)

        for key in discard_invoices:
            subcategory_data.pop(key)

    return {
        "data": {
            "version": "GST3.0.4",
            "gstin": company_gstin,
            "hash": "hash",
            "fp": period,
            **convert_to_gov_data_format(data),
        },
        "filename": f"{period}-{company_gstin}.json",
    }


#################################
##### Process Data #############
################################
class GSTR1ProcessData:

    def get_transaction_type(self, invoice):
        if invoice.is_debit_note:
            return "Debit Note"
        elif invoice.is_return:
            return "Credit Note"
        else:
            return "Invoice"

    def process_data_for_invoice_no_key(self, invoice, prepared_data):
        invoice_sub_category = invoice.invoice_sub_category
        invoice_no = invoice.invoice_no

        mapped_dict = prepared_data.setdefault(invoice_sub_category, {}).setdefault(
            invoice_no,
            {
                GSTR1_DataFields.TRANSACTION_TYPE.value: self.get_transaction_type(
                    invoice
                ),
                GSTR1_DataFields.CUST_GSTIN.value: invoice.billing_address_gstin,
                GSTR1_DataFields.CUST_NAME.value: invoice.customer_name,
                GSTR1_DataFields.DOC_DATE.value: invoice.posting_date,
                GSTR1_DataFields.DOC_NUMBER.value: invoice.invoice_no,
                GSTR1_DataFields.DOC_VALUE.value: invoice.invoice_total,
                GSTR1_DataFields.POS.value: invoice.place_of_supply,
                GSTR1_DataFields.REVERSE_CHARGE.value: (
                    "Y" if invoice.is_reverse_charge else "N"
                ),
                GSTR1_DataFields.DOC_TYPE.value: invoice.invoice_type,
                GSTR1_DataFields.TAXABLE_VALUE.value: 0,
                GSTR1_DataFields.IGST.value: 0,
                GSTR1_DataFields.CGST.value: 0,
                GSTR1_DataFields.SGST.value: 0,
                GSTR1_DataFields.CESS.value: 0,
                GSTR1_DataFields.DIFF_PERCENTAGE.value: 0,
                "items": [],
            },
        )

        items = mapped_dict["items"]

        for item in items:
            if item[GSTR1_ItemFields.TAX_RATE.value] == invoice.gst_rate:
                item[GSTR1_ItemFields.TAXABLE_VALUE.value] += invoice.taxable_value
                item[GSTR1_ItemFields.IGST.value] += invoice.igst_amount
                item[GSTR1_ItemFields.CGST.value] += invoice.cgst_amount
                item[GSTR1_ItemFields.SGST.value] += invoice.sgst_amount
                item[GSTR1_ItemFields.CESS.value] += invoice.total_cess_amount
                self.update_totals(mapped_dict, invoice)
                return

        items.append(
            {
                GSTR1_ItemFields.TAXABLE_VALUE.value: invoice.taxable_value,
                GSTR1_ItemFields.IGST.value: invoice.igst_amount,
                GSTR1_ItemFields.CGST.value: invoice.cgst_amount,
                GSTR1_ItemFields.SGST.value: invoice.sgst_amount,
                GSTR1_ItemFields.CESS.value: invoice.total_cess_amount,
                GSTR1_ItemFields.TAX_RATE.value: invoice.gst_rate,
            }
        )

        self.update_totals(mapped_dict, invoice)

    def process_data_for_document_category_key(self, invoice, prepared_data):
        key = invoice.invoice_category
        mapped_dict = prepared_data.setdefault(key, {}).setdefault(
            invoice.invoice_type, []
        )

        for row in mapped_dict:
            if row[GSTR1_DataFields.DOC_NUMBER.value] == invoice.invoice_no:
                self.update_totals(row, invoice)
                return

        mapped_dict.append(
            {
                GSTR1_DataFields.TRANSACTION_TYPE.value: self.get_transaction_type(
                    invoice
                ),
                GSTR1_DataFields.DOC_NUMBER.value: invoice.invoice_no,
                GSTR1_DataFields.DOC_DATE.value: invoice.posting_date,
                **self.get_invoice_values(invoice),
            }
        )

    def process_data_for_b2cs(self, invoice, prepared_data):
        key = f"{invoice.place_of_supply} - {flt(invoice.gst_rate)} - {invoice.ecommerce_gstin or ''}"
        mapped_dict = prepared_data.setdefault("B2C (Others)", {}).setdefault(key, [])

        for row in mapped_dict:
            if row[GSTR1_DataFields.DOC_NUMBER.value] == invoice.invoice_no:
                self.update_totals(row, invoice)
                return

        mapped_dict.append(
            {
                GSTR1_DataFields.TRANSACTION_TYPE.value: self.get_transaction_type(
                    invoice
                ),
                GSTR1_DataFields.DOC_NUMBER.value: invoice.invoice_no,
                GSTR1_DataFields.POS.value: invoice.place_of_supply,
                GSTR1_DataFields.TAX_RATE.value: invoice.gst_rate,
                GSTR1_DataFields.ECOMMERCE_GSTIN.value: invoice.ecommerce_gstin,
                **self.get_invoice_values(invoice),
            }
        )

    def process_data_for_hsn_summary(self, invoice, prepared_data):
        key = f"{invoice.gst_hsn_code} - {invoice.stock_uom} - {flt(invoice.gst_rate)}"

        if key not in prepared_data:
            mapped_dict = prepared_data.setdefault(
                key,
                {
                    GSTR1_DataFields.HSN_CODE.value: invoice.gst_hsn_code,
                    GSTR1_DataFields.DESCRIPTION.value: frappe.db.get_value(
                        "GST HSN Code", invoice.gst_hsn_code, "description"
                    ),
                    GSTR1_DataFields.UOM.value: invoice.stock_uom,
                    GSTR1_DataFields.QUANTITY.value: 0,
                    GSTR1_DataFields.TAX_RATE.value: invoice.gst_rate,
                    GSTR1_DataFields.TAXABLE_VALUE.value: 0,
                    GSTR1_DataFields.IGST.value: 0,
                    GSTR1_DataFields.CGST.value: 0,
                    GSTR1_DataFields.SGST.value: 0,
                    GSTR1_DataFields.CESS.value: 0,
                },
            )

        else:
            mapped_dict = prepared_data[key]

        self.update_totals(mapped_dict, invoice, for_qty=True)

    def process_data_for_document_issued_summary(self, row, prepared_data):
        key = f"{row['nature_of_document']} - {row['from_serial_no']}"
        prepared_data.setdefault(
            key,
            {
                GSTR1_DataFields.DOC_TYPE.value: row["nature_of_document"],
                GSTR1_DataFields.FROM_SR.value: row["from_serial_no"],
                GSTR1_DataFields.TO_SR.value: row["to_serial_no"],
                GSTR1_DataFields.TOTAL_COUNT.value: row["total_issued"],
                GSTR1_DataFields.DRAFT_COUNT.value: row["total_draft"],
                GSTR1_DataFields.CANCELLED_COUNT.value: row["cancelled"],
            },
        )

    def process_data_for_advances_received_or_adjusted(self, row, prepared_data):
        advances = {}
        tax_rate = round(((row["tax_amount"] / row["taxable_value"]) * 100))
        key = f"{row['place_of_supply']} - {flt(tax_rate)}"

        mapped_dict = prepared_data.setdefault(key, [])

        advances[GSTR1_DataFields.CUST_NAME.value] = row["party"]
        advances[GSTR1_DataFields.DOC_NUMBER.value] = row["name"]
        advances[GSTR1_DataFields.DOC_DATE.value] = row["posting_date"]
        advances[GSTR1_DataFields.POS.value] = row["place_of_supply"]
        advances[GSTR1_DataFields.TAXABLE_VALUE.value] = row["taxable_value"]
        advances[GSTR1_DataFields.TAX_RATE.value] = tax_rate
        advances[GSTR1_DataFields.CESS.value] = row["cess_amount"]

        if row.get("reference_name"):
            advances["against_voucher"] = row["reference_name"]

        if row["place_of_supply"][0:2] == row["company_gstin"][0:2]:
            advances[GSTR1_DataFields.CGST.value] = row["tax_amount"] / 2
            advances[GSTR1_DataFields.SGST.value] = row["tax_amount"] / 2
            advances[GSTR1_DataFields.IGST.value] = 0

        else:
            advances[GSTR1_DataFields.IGST.value] = row["tax_amount"]
            advances[GSTR1_DataFields.CGST.value] = 0
            advances[GSTR1_DataFields.SGST.value] = 0

        mapped_dict.append(advances)

    # utils

    def update_totals(self, mapped_dict, invoice, for_qty=False):
        data_invoice_amount_map = {
            GSTR1_DataFields.TAXABLE_VALUE.value: GSTR1_ItemFields.TAXABLE_VALUE.value,
            GSTR1_DataFields.IGST.value: GSTR1_ItemFields.IGST.value,
            GSTR1_DataFields.CGST.value: GSTR1_ItemFields.CGST.value,
            GSTR1_DataFields.SGST.value: GSTR1_ItemFields.SGST.value,
            GSTR1_DataFields.CESS.value: GSTR1_ItemFields.CESS.value,
        }

        if for_qty:
            data_invoice_amount_map[GSTR1_DataFields.QUANTITY.value] = "qty"

        for key, field in data_invoice_amount_map.items():
            mapped_dict[key] += invoice.get(field, 0)

    def get_invoice_values(self, invoice):
        return {
            GSTR1_DataFields.TAXABLE_VALUE.value: invoice.taxable_value,
            GSTR1_DataFields.IGST.value: invoice.igst_amount,
            GSTR1_DataFields.CGST.value: invoice.cgst_amount,
            GSTR1_DataFields.SGST.value: invoice.sgst_amount,
            GSTR1_DataFields.CESS.value: invoice.total_cess_amount,
        }


def test_gstr1_mapped_data():
    filters = frappe._dict(
        {
            "company": "Shalibhadra Metal Corporation",
            "company_gstin": "24AAUPV7468F1ZW",
            "from_date": getdate("2024-03-01"),
            "to_date": get_last_day("2024-03-01"),
        }
    )

    return GSTR1MappedData(filters).prepare_mapped_data()


class GSTR1MappedData(GSTR1ProcessData):
    def __init__(self, filters):
        self.filters = filters

    def prepare_mapped_data(self):
        prepared_data = {}

        _class = GSTR1Invoices(self.filters)
        data = _class.get_invoices_for_item_wise_summary()
        _class.process_invoices(data)

        for invoice in data:
            if invoice["invoice_category"] in (
                GSTR1_Categories.B2B.value,
                GSTR1_Categories.EXP.value,
                GSTR1_Categories.B2CL.value,
                GSTR1_Categories.CDNR.value,
                GSTR1_Categories.CDNUR.value,
            ):
                self.process_data_for_invoice_no_key(invoice, prepared_data)
            elif invoice["invoice_category"] == GSTR1_Categories.NIL_EXEMPT.value:
                self.process_data_for_document_category_key(invoice, prepared_data)
            elif invoice["invoice_category"] == GSTR1_Categories.B2CS.value:
                self.process_data_for_b2cs(invoice, prepared_data)

        other_categories = {
            GSTR1_Categories.AT.value: self.prepare_advances_recevied_data(),
            GSTR1_Categories.TXP.value: self.prepare_advances_adjusted_data(),
            GSTR1_Categories.HSN.value: self.prepare_hsn_data(data),
            GSTR1_Categories.DOC_ISSUE.value: self.prepare_document_issued_data(),
        }

        for category, data in other_categories.items():
            if data:
                prepared_data[category] = data

        return prepared_data

    def prepare_document_issued_data(self):
        doc_issued_data = {}
        data = GSTR1DocumentIssuedSummary(self.filters).get_data()

        for row in data:
            self.process_data_for_document_issued_summary(row, doc_issued_data)

        return doc_issued_data

    def prepare_hsn_data(self, data):
        hsn_summary_data = {}

        for row in data:
            self.process_data_for_hsn_summary(row, hsn_summary_data)

        return hsn_summary_data

    def prepare_advances_recevied_data(self):
        return self.prepare_advances_received_or_adjusted_data("Advances")

    def prepare_advances_adjusted_data(self):
        return self.prepare_advances_received_or_adjusted_data("Adjustment")

    def prepare_advances_received_or_adjusted_data(self, type_of_business):
        advances_data = {}
        self.filters.type_of_business = type_of_business
        gst_accounts = get_gst_accounts_by_type(self.filters.company, "Output")
        _class = GSTR11A11BData(self.filters, gst_accounts)

        if type_of_business == "Advances":
            query = _class.get_11A_query()
            fields = (
                _class.pe.name,
                _class.pe.party,
                _class.pe.posting_date,
                _class.pe.company_gstin,
            )
        elif type_of_business == "Adjustment":
            query = _class.get_11B_query()
            fields = (
                _class.pe.name,
                _class.pe.party,
                _class.pe.posting_date,
                _class.pe.company_gstin,
                _class.pe_ref.reference_name,
            )

        query = query.select(*fields)
        data = query.run(as_dict=True)

        for row in data:
            self.process_data_for_advances_received_or_adjusted(row, advances_data)

        return advances_data


class BooksExcel:

    AMOUNT_HEADERS = [
        {"fieldname": GSTR1_DataFields.IGST.value, "label": "IGST"},
        {"fieldname": GSTR1_DataFields.CGST.value, "label": "CGST"},
        {"fieldname": GSTR1_DataFields.SGST.value, "label": "SGST"},
        {"fieldname": GSTR1_DataFields.CESS.value, "label": "CESS"},
    ]

    def __init__(self, company_gstin, month_or_quarter, year):
        self.company_gstin = company_gstin
        self.month_or_quarter = month_or_quarter
        self.year = year

        self.period = get_period(month_or_quarter, year)
        doc = frappe.get_doc("GSTR-1 Filed Log", f"{self.period}-{company_gstin}")
        self.data = doc.load_data("books")["books"]

    def export_data(self):
        excel = ExcelExporter()
        excel.remove_sheet("Sheet")

        excel.create_sheet(
            sheet_name="sales invoice",
            headers=self.get_document_headers(),
            data=self.get_document_data(),
            add_totals=False,
        )
        if hsn_data := self.data.get(GSTR1_SubCategories.HSN.value):
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.HSN.value,
                headers=self.get_hsn_summary_headers(),
                data=hsn_data,
                add_totals=False,
            )

        if at_received_data := self.data.get(GSTR1_SubCategories.AT.value):
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.AT.value,
                headers=self.get_at_received_headers(),
                data=at_received_data,
                add_totals=False,
            )

        if at_adjusted_data := self.data.get(GSTR1_SubCategories.TXP.value):
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.TXP.value,
                headers=self.get_at_adjusted_headers(),
                data=at_adjusted_data,
                add_totals=False,
            )

        if doc_issued_data := self.data.get(GSTR1_SubCategories.DOC_ISSUE.value):
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.DOC_ISSUE.value,
                headers=self.get_doc_issue_headers(),
                data=doc_issued_data,
                add_totals=False,
            )

        excel.export(self.get_file_name())

    def get_file_name(self):
        filename = ["gstr1", "books", self.company_gstin, self.period]
        return "-".join(filename)

    def get_document_data(self):
        category = [
            GSTR1_SubCategories.B2B_REGULAR.value,
            GSTR1_SubCategories.B2B_REVERSE_CHARGE.value,
            GSTR1_SubCategories.SEZWP.value,
            GSTR1_SubCategories.SEZWOP.value,
            GSTR1_SubCategories.DE.value,
            GSTR1_SubCategories.EXPWP.value,
            GSTR1_SubCategories.EXPWOP.value,
            GSTR1_SubCategories.B2CL.value,
            GSTR1_SubCategories.B2CS.value,
            GSTR1_SubCategories.NIL_EXEMPT.value,
            GSTR1_SubCategories.CDNR.value,
            GSTR1_SubCategories.CDNUR.value,
        ]

        category_data = []
        for key, values in self.data.items():
            if key not in category:
                continue

            if key in (
                GSTR1_SubCategories.B2CS.value,
                GSTR1_SubCategories.NIL_EXEMPT.value,
            ):
                category_data.extend(values)
                continue

            for row in values:
                dict = row
                for item in row["items"]:
                    category_data.extend([{**dict, **item}])

        return category_data

    def get_document_headers(self):
        return [
            {
                "label": "Transaction Type",
                "fieldname": GSTR1_DataFields.TRANSACTION_TYPE.value,
            },
            {
                "label": "Document Date",
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
            },
            {
                "label": "Document Number",
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
            },
            {
                "label": "Customer GSTIN",
                "fieldname": GSTR1_DataFields.CUST_GSTIN.value,
            },
            {
                "label": "Customer Name",
                "fieldname": GSTR1_DataFields.CUST_NAME.value,
            },
            {
                "label": "Document Type",
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
            },
            {
                "label": "Shipping Bill Number",
                "fieldname": GSTR1_DataFields.SHIPPING_BILL_NUMBER.value,
            },
            {
                "label": "Shipping Bill Date",
                "fieldname": GSTR1_DataFields.SHIPPING_BILL_DATE.value,
            },
            {
                "label": "Port Code",
                "fieldname": GSTR1_DataFields.SHIPPING_PORT_CODE.value,
            },
            {
                "label": "Reverse Charge",
                "fieldname": GSTR1_DataFields.REVERSE_CHARGE.value,
            },
            {
                "label": "Upload Status",
                "fieldname": GSTR1_DataFields.UPLOAD_STATUS.value,
            },
            {
                "label": "Place of Supply",
                "fieldname": GSTR1_DataFields.POS.value,
            },
            *self.AMOUNT_HEADERS,
            {
                "label": "Document Value",
                "fieldname": GSTR1_DataFields.DOC_VALUE.value,
            },
        ]

    def get_at_received_headers(self):
        return [
            {
                "label": "Advance Date",
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
            },
            {
                "label": "Payment Entry Number",
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
            },
            {
                "label": "Customer",
                "fieldname": GSTR1_DataFields.CUST_NAME.value,
            },
            {
                "label": "Place of Supply",
                "fieldname": GSTR1_DataFields.POS.value,
            },
            *self.AMOUNT_HEADERS,
            {
                "label": "Amount Received",
                "fieldname": GSTR1_DataFields.DOC_VALUE.value,
            },
        ]

    def get_at_adjusted_headers(self):
        return [
            {
                "label": "Adjustment Date",
                "fieldname": GSTR1_DataFields.DOC_DATE,
            },
            {
                "label": "Adjustment Entry Number",
                "fieldname": GSTR1_DataFields.DOC_NUMBER,
            },
            {
                "label": "Customer ",
                "fieldname": GSTR1_DataFields.CUST_NAME,
            },
            {
                "label": "Place of Supply",
                "fieldname": GSTR1_DataFields.POS,
            },
            *self.AMOUNT_HEADERS,
            {
                "label": "Amount Adjusted",
                "fieldname": GSTR1_DataFields.DOC_VALUE,
            },
        ]

    def get_hsn_summary_headers(self):
        return [
            {
                "label": "HSN Code",
                "fieldname": GSTR1_DataFields.HSN_CODE.value,
            },
            {
                "label": "Description",
                "fieldname": GSTR1_DataFields.DESCRIPTION.value,
            },
            {
                "label": "UOM",
                "fieldname": GSTR1_DataFields.UOM.value,
            },
            {
                "label": "Total Quantity",
                "fieldname": GSTR1_DataFields.QUANTITY.value,
            },
            *self.AMOUNT_HEADERS,
        ]

    def get_doc_issue_headers(self):
        return [
            {
                "label": "Document Type",
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
            },
            {
                "label": "Sr No From",
                "fieldname": GSTR1_DataFields.FROM_SR.value,
            },
            {
                "label": "Sr No To",
                "fieldname": GSTR1_DataFields.TO_SR.value,
            },
            {
                "label": "Total Count",
                "fieldname": GSTR1_DataFields.TOTAL_COUNT.value,
            },
            {
                "label": "Draft Count",
                "fieldname": GSTR1_DataFields.DRAFT_COUNT.value,
            },
            {
                "label": "Cancelled Count",
                "fieldname": GSTR1_DataFields.CANCELLED_COUNT.value,
            },
        ]


class ReconcileExcel:

    def __init__(self, company_gstin, month_or_quarter, year):
        self.company_gstin = company_gstin
        self.month_or_quarter = month_or_quarter
        self.year = year

        self.period = get_period(month_or_quarter, year)
        doc = frappe.get_doc("GSTR-1 Filed Log", f"{self.period}-{company_gstin}")

        self.summary = doc.load_data("reconcile_summary")["reconcile_summary"]
        self.data = doc.load_data("reconcile")["reconcile"]

    def export_data(self):
        excel = ExcelExporter()
        excel.remove_sheet("Sheet")

        excel.create_sheet(
            sheet_name="reconcile summary",
            headers=self.get_reconcile_summary_headers(),
            data=self.get_reconcile_summary_data(),
            add_totals=False,
        )

        if b2b_data := self.get_b2b_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.B2B.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_b2b_headers(),
                data=b2b_data,
                add_totals=False,
            )

        if b2cl_data := self.get_b2cl_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.B2CL.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_b2cl_headers(),
                data=b2cl_data,
                add_totals=False,
            )

        if exports_data := self.get_exports_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.EXP.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_exports_headers(),
                data=exports_data,
                add_totals=False,
            )

        if b2cs_data := self.get_b2cs_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.B2CS.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_b2cs_headers(),
                data=b2cs_data,
                add_totals=False,
            )

        if nil_exempt_data := self.get_nil_exempt_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.NIL_EXEMPT.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_nil_exempt_headers(),
                data=nil_exempt_data,
                add_totals=False,
            )

        if cdnr_data := self.get_cdnr_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.CDNR.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_cdnr_headers(),
                data=cdnr_data,
                add_totals=False,
            )

        if cdnur_data := self.get_cdnur_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.CDNUR.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_cdnur_headers(),
                data=cdnur_data,
                add_totals=False,
            )

        if doc_issue_data := self.get_doc_issue_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.DOC_ISSUE.value,
                merged_headers=self.get_merge_headers_for_doc_issue(),
                headers=self.get_doc_issue_headers(),
                data=doc_issue_data,
                add_totals=False,
            )

        if hsn_data := self.get_hsn_summary_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.HSN.value,
                merged_headers=self.get_merge_headers_for_hsn_summary(),
                headers=self.get_hsn_summary_headers(),
                data=hsn_data,
                add_totals=False,
            )

        if at_data := self.get_at_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.AT.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_at_txp_headers(),
                data=at_data,
                add_totals=False,
            )

        if txp_data := self.get_txp_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.TXP.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_at_txp_headers(),
                data=txp_data,
                add_totals=False,
            )

        excel.export(self.get_file_name())

    def get_file_name(self):
        filename = ["gstr1", "reconcile", self.company_gstin, self.period]
        return "-".join(filename)

    def get_merge_headers(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + GSTR1_DataFields.POS.value,
                    "books_" + GSTR1_DataFields.CESS.value,
                ],
                "GSTR-1": [
                    "gstr_1_" + GSTR1_DataFields.POS.value,
                    "gstr_1_" + GSTR1_DataFields.CESS.value,
                ],
            }
        )

    def get_merge_headers_for_doc_issue(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + GSTR1_DataFields.FROM_SR.value,
                    "books_" + GSTR1_DataFields.CANCELLED_COUNT.value,
                ],
                "GSTR-1": [
                    "gstr_1_" + GSTR1_DataFields.FROM_SR.value,
                    "gstr_1_" + GSTR1_DataFields.CANCELLED_COUNT.value,
                ],
            }
        )

    def get_merge_headers_for_hsn_summary(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + GSTR1_DataFields.UOM.value,
                    "books_" + GSTR1_DataFields.CESS.value,
                ],
                "GSTR-1": [
                    "gstr_1_" + GSTR1_DataFields.UOM.value,
                    "gstr_1_" + GSTR1_DataFields.CESS.value,
                ],
            }
        )

    def get_reconcile_summary_headers(self):
        headers = [
            {
                "fieldname": "description",
                "label": "Description",
            },
            {
                "fieldname": "total_taxable_value",
                "label": "Taxable Value",
            },
            {
                "fieldname": "total_igst_amount",
                "label": "IGST",
            },
            {
                "fieldname": "total_cgst_amount",
                "label": "CGST",
            },
            {
                "fieldname": "total_sgst_amount",
                "label": "SGST",
            },
            {
                "fieldname": "total_cess_amount",
                "label": "CESS",
            },
        ]
        return headers

    def get_reconcile_summary_data(self):
        excel_data = []
        for row in self.summary:
            if row["indent"] == 1:
                continue
            excel_data.append(row)

        return excel_data

    def get_b2b_headers(self):
        return [
            {
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
                "label": "Document Type",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "label": "Document Date",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "label": "Document No",
            },
            {
                "fieldname": GSTR1_DataFields.CUST_GSTIN.value,
                "label": "Customer GSTIN",
            },
            {"fieldname": GSTR1_DataFields.CUST_NAME.value, "label": "Customer Name"},
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
            },
            {"fieldname": "tax_difference", "label": "Tax Difference"},
            {
                "fieldname": "books_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "gstr_1_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "books_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "books_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "books_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "books_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
        ]

    def get_b2b_data(self):
        b2b_regular = self.data.get(GSTR1_SubCategories.B2B_REGULAR.value, [])
        b2b_reverse_charge = self.data.get(
            GSTR1_SubCategories.B2B_REVERSE_CHARGE.value, []
        )
        sezwop = self.data.get(GSTR1_SubCategories.SEZWOP.value, [])
        sezwp = self.data.get(GSTR1_SubCategories.SEZWP.value, [])
        deemed_export = self.data.get(GSTR1_SubCategories.DE.value, [])

        b2b_data = b2b_regular + b2b_reverse_charge + sezwop + sezwp + deemed_export

        excel_data = []

        for row in b2b_data:
            row_dict = self.get_row_dict(row)

            excel_data.append(row_dict)

        return excel_data

    def get_b2cl_headers(self):
        return [
            {
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
                "label": "Document Type",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "label": "Document Date",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "label": "Document No",
            },
            {"fieldname": GSTR1_DataFields.CUST_NAME.value, "label": "Customer Name"},
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
            },
            {"fieldname": "tax_difference", "label": "Tax Difference"},
            {
                "fieldname": "books_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "gstr_1_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "books_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "books_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
        ]

    def get_b2cl_data(self):
        b2cl_data = self.data.get(GSTR1_SubCategories.B2CL.value, [])

        excel_data = []

        for row in b2cl_data:
            row_dict = self.get_row_dict(row)
            excel_data.append(row_dict)

        return excel_data

    def get_exports_headers(self):
        return [
            {
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
                "label": "Document Type",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "label": "Document Date",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "label": "Document No",
            },
            {"fieldname": GSTR1_DataFields.CUST_NAME.value, "label": "Customer Name"},
            {
                "fieldname": GSTR1_DataFields.SHIPPING_BILL_NUMBER.value,
                "label": "Shipping Bill Number",
            },
            {
                "fieldname": GSTR1_DataFields.SHIPPING_BILL_DATE.value,
                "label": "Shipping Bill Date",
            },
            {
                "fieldname": GSTR1_DataFields.SHIPPING_PORT_CODE.value,
                "label": "Shipping Port Code",
            },
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
            },
            {"fieldname": "tax_difference", "label": "Tax Difference"},
            {
                "fieldname": "books_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "gstr_1_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "books_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "books_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "books_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "books_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
        ]

    def get_exports_data(self):
        expwp = self.data.get(GSTR1_SubCategories.EXPWP.value, [])
        expwop = self.data.get(GSTR1_SubCategories.EXPWOP.value, [])

        exports_data = expwp + expwop

        excel_data = []

        for row in exports_data:
            row_dict = self.get_row_dict(row)
            row_dict.update(
                {
                    GSTR1_DataFields.SHIPPING_BILL_NUMBER.value: row.get(
                        "shipping_bill_number"
                    ),
                    GSTR1_DataFields.SHIPPING_BILL_DATE.value: row.get(
                        "shipping_bill_date"
                    ),
                    GSTR1_DataFields.SHIPPING_PORT_CODE.value: row.get(
                        "shipping_port_code"
                    ),
                }
            )

            excel_data.append(row_dict)

        return excel_data

    def get_b2cs_headers(self):
        return [
            {
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
                "label": "Document Type",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "label": "Document Date",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "label": "Document No",
            },
            {"fieldname": GSTR1_DataFields.CUST_NAME.value, "label": "Customer Name"},
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
            },
            {"fieldname": "tax_difference", "label": "Tax Difference"},
            {
                "fieldname": "books_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "gstr_1_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "books_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "books_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "books_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
        ]

    def get_b2cs_data(self):
        b2cs_data = self.data.get(GSTR1_SubCategories.B2CS.value, [])

        excel_data = []

        for row in b2cs_data:
            row_dict = self.get_row_dict(row)
            excel_data.append(row_dict)

        return excel_data

    def get_nil_exempt_headers(self):
        return [
            {
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
                "label": "Document Type",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "label": "Document Date",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "label": "Document No",
            },
            {
                "fieldname": GSTR1_DataFields.CUST_GSTIN.value,
                "label": "Customer GSTIN",
            },
            {"fieldname": GSTR1_DataFields.CUST_NAME.value, "label": "Customer Name"},
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
            },
            {"fieldname": "tax_difference", "label": "Tax Difference"},
            {
                "fieldname": "books_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "gstr_1_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "books_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "books_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "books_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "books_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
        ]

    def get_nil_exempt_data(self):
        nil_exempt_data = self.data.get(GSTR1_SubCategories.NIL_EXEMPT.value, [])

        excel_data = []

        for row in nil_exempt_data:
            row_dict = self.get_row_dict(row)
            excel_data.append(row_dict)

        return excel_data

    def get_cdnr_headers(self):
        return [
            {
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
                "label": "Document Type",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "label": "Document Date",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "label": "Document No",
            },
            {
                "fieldname": GSTR1_DataFields.CUST_GSTIN.value,
                "label": "Customer GSTIN",
            },
            {"fieldname": GSTR1_DataFields.CUST_NAME.value, "label": "Customer Name"},
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
            },
            {"fieldname": "tax_difference", "label": "Tax Difference"},
            {
                "fieldname": "books_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "gstr_1_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "books_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "books_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "books_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "books_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
        ]

    def get_cdnr_data(self):
        cdnr_data = self.data.get(GSTR1_SubCategories.CDNR.value, [])

        excel_data = []

        for row in cdnr_data:
            row_dict = self.get_row_dict(row)
            excel_data.append(row_dict)

        return excel_data

    def get_cdnur_headers(self):
        return [
            {
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
                "label": "Document Type",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "label": "Document Date",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "label": "Document No",
            },
            {
                "fieldname": GSTR1_DataFields.CUST_GSTIN.value,
                "label": "Customer GSTIN",
            },
            {"fieldname": GSTR1_DataFields.CUST_NAME.value, "label": "Customer Name"},
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
            },
            {"fieldname": "tax_difference", "label": "Tax Difference"},
            {
                "fieldname": "books_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "gstr_1_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "books_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "books_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "books_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "books_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
        ]

    def get_cdnur_data(self):
        cdnr_data = self.data.get(GSTR1_SubCategories.CDNUR.value, [])

        excel_data = []

        for row in cdnr_data:
            row_dict = self.get_row_dict(row)
            excel_data.append(row_dict)

        return excel_data

    def get_doc_issue_headers(self):
        headers = [
            {"fieldname": GSTR1_DataFields.DOC_TYPE.value, "label": "Document Type"},
            {
                "fieldname": "match_status",
                "label": "Match Status",
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.FROM_SR.value,
                "label": "SR No From",
                "compare_with": "gstr_1_" + GSTR1_DataFields.FROM_SR.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TO_SR.value,
                "label": "SR No To",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TO_SR.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TOTAL_COUNT.value,
                "label": "Total Count",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TOTAL_COUNT.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CANCELLED_COUNT.value,
                "label": "Cancelled Count",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CANCELLED_COUNT.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.FROM_SR.value,
                "label": "Sr No From",
                "compare_with": "books_" + GSTR1_DataFields.FROM_SR.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TO_SR.value,
                "label": "Sr No To",
                "compare_with": "books_" + GSTR1_DataFields.TO_SR.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TOTAL_COUNT.value,
                "label": "Total Count",
                "compare_with": "books_" + GSTR1_DataFields.TOTAL_COUNT.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CANCELLED_COUNT.value,
                "label": "Cancelled Count",
                "compare_with": "books_" + GSTR1_DataFields.CANCELLED_COUNT.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
        ]

        return headers

    def get_doc_issue_data(self):
        doc_issue_data = self.data.get(GSTR1_SubCategories.DOC_ISSUE.value, [])

        excel_data = []

        for row in doc_issue_data:
            books = row.get("books", {})
            gstr_1 = row.get("gov", {})
            row_dict = {
                GSTR1_DataFields.DOC_TYPE.value: row.get(
                    GSTR1_DataFields.DOC_TYPE.value
                ),
                "match_status": row.get("match_status"),
                "books_"
                + GSTR1_DataFields.FROM_SR.value: books.get(
                    GSTR1_DataFields.FROM_SR.value
                ),
                "books_"
                + GSTR1_DataFields.TO_SR.value: books.get(GSTR1_DataFields.TO_SR.value),
                "books_"
                + GSTR1_DataFields.TOTAL_COUNT.value: books.get(
                    GSTR1_DataFields.TOTAL_COUNT.value
                ),
                "books_"
                + GSTR1_DataFields.CANCELLED_COUNT.value: (
                    books.get(GSTR1_DataFields.CANCELLED_COUNT.value) or 0
                )
                + (books.get(GSTR1_DataFields.DRAFT_COUNT.value) or 0),
                "gstr_1_"
                + GSTR1_DataFields.FROM_SR.value: gstr_1.get(
                    GSTR1_DataFields.FROM_SR.value
                ),
                "gstr_1_"
                + GSTR1_DataFields.TO_SR.value: gstr_1.get(
                    GSTR1_DataFields.TO_SR.value
                ),
                "gstr_1_"
                + GSTR1_DataFields.TOTAL_COUNT.value: gstr_1.get(
                    GSTR1_DataFields.TOTAL_COUNT.value
                ),
                "gstr_1_"
                + GSTR1_DataFields.CANCELLED_COUNT.value: (
                    gstr_1.get(GSTR1_DataFields.CANCELLED_COUNT.value) or 0
                )
                + (gstr_1.get(GSTR1_DataFields.DRAFT_COUNT.value) or 0),
            }

            excel_data.append(row_dict)

        return excel_data

    def get_hsn_summary_headers(self):
        headers = [
            {"fieldname": GSTR1_DataFields.HSN_CODE.value, "label": "HSN Code"},
            {"fieldname": GSTR1_DataFields.DESCRIPTION.value, "label": "Description"},
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
            },
            {"fieldname": "tax_difference", "label": "Tax Difference"},
            {
                "fieldname": "books_" + GSTR1_DataFields.UOM.value,
                "label": "UQC",
                "compare_with": "gstr_1_" + GSTR1_DataFields.UOM.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.QUANTITY.value,
                "label": "Quantity",
                "compare_with": "gstr_1_" + GSTR1_DataFields.QUANTITY.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.IGST.value,
                "label": "IGST Amount",
                "compare_with": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CGST.value,
                "label": "CGST Amount",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.SGST.value,
                "label": "SGST Amount",
                "compare_with": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS Amount",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.UOM.value,
                "label": "UQC",
                "compare_with": "books_" + GSTR1_DataFields.UOM.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.QUANTITY.value,
                "label": "Quantity",
                "compare_with": "books_" + GSTR1_DataFields.QUANTITY.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "label": "IGST Amount",
                "compare_with": "books_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "label": "CGST Amount",
                "compare_with": "books_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "label": "SGST Amount",
                "compare_with": "books_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS Amount",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
        ]

        return headers

    def get_hsn_summary_data(self):
        hsn_summary_data = self.data.get(GSTR1_SubCategories.HSN.value, [])

        excel_data = []

        for row in hsn_summary_data:
            books = row.get("books", {})
            gstr_1 = row.get("gov", {})

            row_dict = {
                GSTR1_DataFields.HSN_CODE.value: row.get(
                    GSTR1_DataFields.HSN_CODE.value
                ),
                GSTR1_DataFields.DESCRIPTION.value: row.get(
                    GSTR1_DataFields.DESCRIPTION.value
                ),
                "match_status": row.get("match_status"),
                "books_"
                + GSTR1_DataFields.UOM.value: books.get(GSTR1_DataFields.UOM.value),
                "books_"
                + GSTR1_DataFields.QUANTITY.value: books.get(
                    GSTR1_DataFields.QUANTITY.value
                ),
                "books_"
                + GSTR1_DataFields.TAX_RATE.value: books.get(
                    GSTR1_DataFields.TAX_RATE.value
                ),
                "books_"
                + GSTR1_DataFields.TAXABLE_VALUE.value: books.get(
                    GSTR1_DataFields.TAXABLE_VALUE.value
                ),
                "books_"
                + GSTR1_DataFields.IGST.value: books.get(GSTR1_DataFields.IGST.value),
                "books_"
                + GSTR1_DataFields.CGST.value: books.get(GSTR1_DataFields.CGST.value),
                "books_"
                + GSTR1_DataFields.SGST.value: books.get(GSTR1_DataFields.SGST.value),
                "books_"
                + GSTR1_DataFields.CESS.value: books.get(GSTR1_DataFields.CESS.value),
                "gstr_1_"
                + GSTR1_DataFields.UOM.value: gstr_1.get(GSTR1_DataFields.UOM.value),
                "gstr_1_"
                + GSTR1_DataFields.QUANTITY.value: gstr_1.get(
                    GSTR1_DataFields.QUANTITY.value
                ),
                "gstr_1_"
                + GSTR1_DataFields.TAX_RATE.value: gstr_1.get(
                    GSTR1_DataFields.TAX_RATE.value
                ),
                "gstr_1_"
                + GSTR1_DataFields.TAXABLE_VALUE.value: gstr_1.get(
                    GSTR1_DataFields.TAXABLE_VALUE.value
                ),
                "gstr_1_"
                + GSTR1_DataFields.IGST.value: gstr_1.get(GSTR1_DataFields.IGST.value),
                "gstr_1_"
                + GSTR1_DataFields.CGST.value: gstr_1.get(GSTR1_DataFields.CGST.value),
                "gstr_1_"
                + GSTR1_DataFields.SGST.value: gstr_1.get(GSTR1_DataFields.SGST.value),
                "gstr_1_"
                + GSTR1_DataFields.CESS.value: gstr_1.get(GSTR1_DataFields.CESS.value),
            }

            self.get_taxable_value_difference(row_dict)
            self.get_tax_difference(row_dict)

            excel_data.append(row_dict)

        return excel_data

    def get_at_txp_headers(self):
        return [
            {"fieldname": GSTR1_DataFields.DOC_DATE.value, "label": "Advance Date"},
            {
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "label": "Payment Entry Number",
            },
            {"fieldname": GSTR1_DataFields.CUST_NAME.value, "label": "Customer Name"},
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
            },
            {"fieldname": "tax_difference", "label": "Tax Difference"},
            {
                "fieldname": "books_" + GSTR1_DataFields.POS.value,
                "label": "POS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.POS.value,
                "label": "POS",
                "compare_with": "books_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "books_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "books_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "books_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": COLOR_PALLATE.sky_blue,
                },
            },
        ]

    def get_at_data(self):
        at_data = self.data.get(GSTR1_SubCategories.AT.value, [])

        excel_data = []
        for row in at_data:
            row_dict = self.get_row_dict(row)
            excel_data.append(row_dict)

        return excel_data

    def get_txp_data(self):
        txp_adjusted = self.data.get(GSTR1_SubCategories.TXP.value, [])

        excel_data = []
        for row in txp_adjusted:
            row_dict = self.get_row_dict(row)
            excel_data.append(row_dict)

        return excel_data

    def get_row_dict(self, row):
        books = row.get("books", {})
        gstr_1 = row.get("gov", {})

        row_dict = {
            GSTR1_DataFields.DOC_DATE.value: row.get(GSTR1_DataFields.DOC_DATE.value),
            GSTR1_DataFields.DOC_NUMBER.value: row.get(
                GSTR1_DataFields.DOC_NUMBER.value
            ),
            GSTR1_DataFields.CUST_NAME.value: row.get(GSTR1_DataFields.CUST_NAME.value),
            GSTR1_DataFields.CUST_GSTIN.value: row.get(
                GSTR1_DataFields.CUST_GSTIN.value
            ),
            GSTR1_DataFields.DOC_TYPE.value: row.get(GSTR1_DataFields.DOC_TYPE.value),
            "match_status": row.get("match_status"),
            "books_"
            + GSTR1_DataFields.POS.value: books.get(GSTR1_DataFields.POS.value),
            "books_"
            + GSTR1_DataFields.TAX_RATE.value: books.get(
                GSTR1_DataFields.TAX_RATE.value
            ),
            "books_"
            + GSTR1_DataFields.REVERSE_CHARGE.value: books.get(
                GSTR1_DataFields.REVERSE_CHARGE.value
            ),
            "books_"
            + GSTR1_DataFields.TAXABLE_VALUE.value: books.get(
                GSTR1_DataFields.TAXABLE_VALUE.value
            ),
            "books_"
            + GSTR1_DataFields.IGST.value: books.get(GSTR1_DataFields.IGST.value),
            "books_"
            + GSTR1_DataFields.CGST.value: books.get(GSTR1_DataFields.CGST.value),
            "books_"
            + GSTR1_DataFields.SGST.value: books.get(GSTR1_DataFields.SGST.value),
            "books_"
            + GSTR1_DataFields.CESS.value: books.get(GSTR1_DataFields.CESS.value),
            "gstr_1_"
            + GSTR1_DataFields.POS.value: gstr_1.get(GSTR1_DataFields.POS.value),
            "gstr_1_"
            + GSTR1_DataFields.TAX_RATE.value: gstr_1.get(
                GSTR1_DataFields.TAX_RATE.value
            ),
            "gstr_1_"
            + GSTR1_DataFields.REVERSE_CHARGE.value: gstr_1.get(
                GSTR1_DataFields.REVERSE_CHARGE.value
            ),
            "gstr_1_"
            + GSTR1_DataFields.TAXABLE_VALUE.value: gstr_1.get(
                GSTR1_DataFields.TAXABLE_VALUE.value
            ),
            "gstr_1_"
            + GSTR1_DataFields.IGST.value: gstr_1.get(GSTR1_DataFields.IGST.value),
            "gstr_1_"
            + GSTR1_DataFields.CGST.value: gstr_1.get(GSTR1_DataFields.CGST.value),
            "gstr_1_"
            + GSTR1_DataFields.SGST.value: gstr_1.get(GSTR1_DataFields.SGST.value),
            "gstr_1_"
            + GSTR1_DataFields.CESS.value: gstr_1.get(GSTR1_DataFields.CESS.value),
        }

        self.get_taxable_value_difference(row_dict)
        self.get_tax_difference(row_dict)

        return row_dict

    def get_taxable_value_difference(self, row_dict):
        row_dict["taxable_value_difference"] = (
            row_dict["books_" + GSTR1_DataFields.TAXABLE_VALUE.value] or 0
        ) - (row_dict["gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value] or 0)

    def get_tax_difference(self, row_dict):
        row_dict["tax_difference"] = (
            (row_dict["books_" + GSTR1_DataFields.IGST.value] or 0)
            - (row_dict["gstr_1_" + GSTR1_DataFields.IGST.value] or 0)
            + (
                (row_dict["books_" + GSTR1_DataFields.CGST.value] or 0)
                - (row_dict["gstr_1_" + GSTR1_DataFields.CGST.value] or 0)
            )
            + (
                (row_dict["books_" + GSTR1_DataFields.SGST.value] or 0)
                - (row_dict["gstr_1_" + GSTR1_DataFields.SGST.value] or 0)
            )
            + (
                (row_dict["books_" + GSTR1_DataFields.CESS.value] or 0)
                - (row_dict["gstr_1_" + GSTR1_DataFields.CESS.value] or 0)
            )
        )
