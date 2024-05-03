# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

from datetime import datetime

import frappe
from frappe import _, unscrub
from frappe.model.document import Document
from frappe.query_builder.functions import Date, Sum
from frappe.utils import flt, get_last_day, getdate

from india_compliance.gst_india.doctype.gstr_1_filed_log.gstr_1_filed_log import (
    summarize_data,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import (
    summarize_retsum_data,
)
from india_compliance.gst_india.report.gstr_1.gstr_1 import (
    GSTR1DocumentIssuedSummary,
    GSTR11A11BData,
)
from india_compliance.gst_india.utils.__init__ import get_gst_accounts_by_type
from india_compliance.gst_india.utils.gstin_info import get_gstr_1_return_status
from india_compliance.gst_india.utils.gstr_1 import (
    INVOICE_SUB_CATEGORIES,
    DataFields,
    GSTR1_Categories,
    ItemFields,
    GSTR1_SubCategories,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_data import GSTR1Invoices
from india_compliance.gst_india.utils.gstr_1.gstr_1_download import (
    download_gstr1_json_data,
)
from india_compliance.gst_india.utils.gstr_utils import request_otp

AMOUNT_FIELDS = {
    "total_taxable_value": 0,
    "total_igst_amount": 0,
    "total_cgst_amount": 0,
    "total_sgst_amount": 0,
    "total_cess_amount": 0,
}


class GSTR1Beta(Document):

    def onload(self):
        data = getattr(self, "data", None)
        if data is not None:
            self.set_onload("data", data)

    @frappe.whitelist()
    def re_download_gstr1(self, file_field):
        if not self.has_permission("write"):
            frappe.throw(_("Not permitted"), frappe.PermissionError)

        self.validate(re_download_file=file_field)

    def validate(self, re_download_file=None):
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
            gstr1_log.gstin = self.company_gstin
            gstr1_log.return_period = period
            gstr1_log.insert()

        settings = frappe.get_cached_doc("GST Settings")

        if re_download_file:
            gstr1_log.remove_json_for(re_download_file)
            gstr1_log.remove_json_for("reconcile")

        # files are already present
        if gstr1_log.has_all_files(settings):
            self.data = gstr1_log.load_data()
            self.data["status"] = gstr1_log.filing_status or "Not Filed"
            gstr1_log.update_status("Generated")
            self.data["computed_on"] = gstr1_log.computed_on
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
        frappe.enqueue(self.generate_gstr1, queue="long")
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

            data["computed_on"] = self.gstr1_log.computed_on

            frappe.publish_realtime(
                "gstr1_data_prepared",
                message={"data": data, "filters": filters},
                user=frappe.session.user,
                doctype=self.doctype,
            )

        # APIs Disabled
        if not self.settings.analyze_filed_data:
            books_data = compute_books_gstr1_data(self)

            data["status"] = "Not Filed"
            data["books"] = self.gstr1_log.normalize_data(books_data)

            on_generate()
            return

        # APIs Enabled
        status = self.gstr1_log.filing_status
        if not status:
            status = get_gstr_1_return_status(
                self.gstr1_log.gstin, self.gstr1_log.return_period
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
    # TODO: compute from and to date for report
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
@frappe.whitelist()
def get_gstr1_filing_frequency():
    gst_settings = frappe.get_cached_doc("GST Settings")
    return gst_settings.filing_frequency


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
def download_books_as_excel(data):
    return "Data Downloaded to Excel Successfully"


@frappe.whitelist()
def download_reconcile_as_excel(data):
    return "Data Downloaded to Excel Successfully"


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
                DataFields.TRANSACTION_TYPE.value: self.get_transaction_type(invoice),
                DataFields.CUST_GSTIN.value: invoice.billing_address_gstin,
                DataFields.CUST_NAME.value: invoice.customer_name,
                DataFields.DOC_DATE.value: invoice.posting_date,
                DataFields.DOC_NUMBER.value: invoice.invoice_no,
                DataFields.DOC_VALUE.value: invoice.invoice_total,
                DataFields.POS.value: invoice.place_of_supply,
                DataFields.REVERSE_CHARGE.value: (
                    "Y" if invoice.is_reverse_charge else "N"
                ),
                DataFields.DOC_TYPE.value: invoice.invoice_type,
                DataFields.TAXABLE_VALUE.value: 0,
                DataFields.IGST.value: 0,
                DataFields.CGST.value: 0,
                DataFields.SGST.value: 0,
                DataFields.CESS.value: 0,
                DataFields.DIFF_PERCENTAGE.value: 0,
                "items": [],
            },
        )

        idx = len(mapped_dict["items"]) + 1

        mapped_dict["items"].append(
            {
                ItemFields.INDEX.value: idx,
                ItemFields.TAXABLE_VALUE.value: invoice.taxable_value,
                ItemFields.IGST.value: invoice.igst_amount,
                ItemFields.CGST.value: invoice.cgst_amount,
                ItemFields.SGST.value: invoice.sgst_amount,
                ItemFields.CESS.value: invoice.total_cess_amount,
            }
        )
        self.update_totals(mapped_dict, invoice)

    def process_data_for_document_category_key(self, invoice, prepared_data):
        key = invoice.invoice_category
        mapped_dict = prepared_data.setdefault(key, {}).setdefault(
            invoice.invoice_type, []
        )

        for row in mapped_dict:
            if row[DataFields.DOC_NUMBER.value] == invoice.invoice_no:
                self.update_totals(row, invoice)
                return

        mapped_dict.append(
            {
                DataFields.TRANSACTION_TYPE.value: self.get_transaction_type(invoice),
                DataFields.DOC_NUMBER.value: invoice.invoice_no,
                DataFields.DOC_DATE.value: invoice.posting_date,
                **self.get_invoice_values(invoice),
            }
        )

    def process_data_for_b2cs(self, invoice, prepared_data):
        key = f"{invoice.place_of_supply} - {flt(invoice.gst_rate)} - {invoice.ecommerce_gstin or ''}"
        mapped_dict = prepared_data.setdefault("B2C (Others)", {}).setdefault(key, [])

        for row in mapped_dict:
            if row[DataFields.DOC_NUMBER.value] == invoice.invoice_no:
                self.update_totals(row, invoice)
                return

        mapped_dict.append(
            {
                DataFields.TRANSACTION_TYPE.value: self.get_transaction_type(invoice),
                DataFields.DOC_NUMBER.value: invoice.invoice_no,
                DataFields.POS.value: invoice.place_of_supply,
                DataFields.TAX_RATE.value: invoice.gst_rate,
                DataFields.ECOMMERCE_GSTIN.value: invoice.ecommerce_gstin,
                **self.get_invoice_values(invoice),
            }
        )

    def process_data_for_hsn_summary(self, invoice, prepared_data):
        key = f"{invoice.gst_hsn_code} - {invoice.stock_uom} - {flt(invoice.gst_rate)}"

        if key not in prepared_data:
            mapped_dict = prepared_data.setdefault(
                key,
                {
                    DataFields.HSN_CODE.value: invoice.gst_hsn_code,
                    DataFields.DESCRIPTION.value: frappe.db.get_value(
                        "GST HSN Code", invoice.gst_hsn_code, "description"
                    ),
                    DataFields.UOM.value: invoice.stock_uom,
                    DataFields.QUANTITY.value: 0,
                    DataFields.TAX_RATE.value: invoice.gst_rate,
                    DataFields.TAXABLE_VALUE.value: 0,
                    DataFields.IGST.value: 0,
                    DataFields.CGST.value: 0,
                    DataFields.SGST.value: 0,
                    DataFields.CESS.value: 0,
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
                DataFields.DOC_TYPE.value: row["nature_of_document"],
                DataFields.FROM_SR.value: row["from_serial_no"],
                DataFields.TO_SR.value: row["to_serial_no"],
                DataFields.TOTAL_COUNT.value: row["total_issued"],
                DataFields.DRAFT_COUNT.value: row["total_draft"],
                DataFields.CANCELLED_COUNT.value: row["cancelled"],
            },
        )

    def process_data_for_advances_received_or_adjusted(self, row, prepared_data):
        advances = {}
        tax_rate = round(((row["tax_amount"] / row["taxable_value"]) * 100))
        key = f"{row['place_of_supply']} - {flt(tax_rate)}"

        mapped_dict = prepared_data.setdefault(key, [])

        advances[DataFields.CUST_NAME.value] = row["party"]
        advances[DataFields.DOC_NUMBER.value] = row["name"]
        advances[DataFields.DOC_DATE.value] = row["posting_date"]
        advances[DataFields.POS.value] = row["place_of_supply"]
        advances[DataFields.TAXABLE_VALUE.value] = row["taxable_value"]
        advances[DataFields.TAX_RATE.value] = tax_rate
        advances[DataFields.CESS.value] = row["cess_amount"]

        if row.get("reference_name"):
            advances["against_voucher"] = row["reference_name"]

        if row["place_of_supply"][0:2] == row["company_gstin"][0:2]:
            advances[DataFields.CGST.value] = row["tax_amount"] / 2
            advances[DataFields.SGST.value] = row["tax_amount"] / 2
            advances[DataFields.IGST.value] = 0

        else:
            advances[DataFields.IGST.value] = row["tax_amount"]
            advances[DataFields.CGST.value] = 0
            advances[DataFields.SGST.value] = 0

        mapped_dict.append(advances)

    # utils

    def update_totals(self, mapped_dict, invoice, for_qty=False):
        data_invoice_amount_map = {
            DataFields.TAXABLE_VALUE.value: ItemFields.TAXABLE_VALUE.value,
            DataFields.IGST.value: ItemFields.IGST.value,
            DataFields.CGST.value: ItemFields.CGST.value,
            DataFields.SGST.value: ItemFields.SGST.value,
            DataFields.CESS.value: ItemFields.CESS.value,
        }

        if for_qty:
            data_invoice_amount_map[DataFields.QUANTITY.value] = "qty"

        for key, field in data_invoice_amount_map.items():
            mapped_dict[key] += invoice.get(field, 0)

    def get_invoice_values(self, invoice):
        return {
            DataFields.TAXABLE_VALUE.value: invoice.taxable_value,
            DataFields.IGST.value: invoice.igst_amount,
            DataFields.CGST.value: invoice.cgst_amount,
            DataFields.SGST.value: invoice.sgst_amount,
            DataFields.CESS.value: invoice.total_cess_amount,
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

        for sub_category_data in prepared_data.values():
            self.set_rounded_values(sub_category_data)

        return prepared_data

    def set_rounded_values(self, data):
        for row in data.values():
            for key in AMOUNT_FIELDS:
                if key not in row:
                    continue

                row[key] = flt(row[key], 2)

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
