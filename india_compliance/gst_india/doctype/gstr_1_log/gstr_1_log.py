# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt
import gzip
import itertools
from datetime import datetime

import frappe
from frappe import _, unscrub
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, get_datetime_str, get_last_day, getdate

from india_compliance.gst_india.utils import is_production_api_enabled
from india_compliance.gst_india.utils.gstr_1 import GSTR1_SubCategory
from india_compliance.gst_india.utils.gstr_1.__init__ import (
    CATEGORY_SUB_CATEGORY_MAPPING,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAX,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE,
    GSTR1_DataField,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_download import (
    download_gstr1_json_data,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import (
    GSTR1BooksData,
    summarize_retsum_data,
)
from india_compliance.gst_india.utils.gstr_utils import request_otp


class SummarizeGSTR1:
    AMOUNT_FIELDS = {
        "total_taxable_value": 0,
        "total_igst_amount": 0,
        "total_cgst_amount": 0,
        "total_sgst_amount": 0,
        "total_cess_amount": 0,
    }

    def get_summarized_data(self, data, is_filed=False):
        """
        Helper function to summarize data for each sub-category
        """
        if is_filed and data.get("summary"):
            return summarize_retsum_data(data.get("summary"))

        subcategory_summary = self.get_subcategory_summary(data)

        return self.get_overall_summary(subcategory_summary)

    def get_overall_summary(self, subcategory_summary):
        """
        Summarize data for each category with subcategories

        Steps:
        1. Init Category row
        2. Summarize category by adding subcategory rows
        3. Remove category row if no records
        4. Round Values
        """
        cateogory_summary = []
        for category, sub_categories in CATEGORY_SUB_CATEGORY_MAPPING.items():
            # Init category row
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
                # update category row
                subcategory = subcategory.value
                if subcategory not in subcategory_summary:
                    continue

                subcategory_row = subcategory_summary[subcategory]
                summary_row["no_of_records"] += subcategory_row["no_of_records"] or 0

                for key in self.AMOUNT_FIELDS:
                    summary_row[key] += subcategory_row[key]

                # add subcategory row
                cateogory_summary.append(subcategory_row)
                remove_category_row = False

            if not summary_row["no_of_records"]:
                summary_row["no_of_records"] = ""

            if remove_category_row:
                cateogory_summary.remove(summary_row)

        # Round Values
        for row in cateogory_summary:
            for key, value in row.items():
                if isinstance(value, (int, float)):
                    row[key] = flt(value, 2)
        return cateogory_summary

    def get_subcategory_summary(self, data):
        """
        Summarize invoices for each subcategory

        Steps:
        1. Init subcategory row
        2. Summarize subcategory by adding invoice rows
        3. Update no_of_records / count for each subcategory
        """
        subcategory_summary = {}

        for subcategory in GSTR1_SubCategory:
            subcategory = subcategory.value
            if subcategory not in data:
                continue

            summary_row = subcategory_summary.setdefault(
                subcategory, self.default_subcategory_summary(subcategory)
            )

            _data = data[subcategory]
            for row in _data:
                if row.get("upload_status") == "Missing in Books":
                    continue

                for key in self.AMOUNT_FIELDS:
                    summary_row[key] += row.get(key, 0)

                if doc_num := row.get("document_number"):
                    summary_row["unique_records"].add(doc_num)

                elif subcategory == GSTR1_SubCategory.DOC_ISSUE.value:
                    self.count_doc_issue_summary(summary_row, row)

                elif subcategory == GSTR1_SubCategory.HSN.value:
                    self.count_hsn_summary(summary_row)

        for subcategory in subcategory_summary.keys():
            summary_row = subcategory_summary[subcategory]
            count = len(summary_row["unique_records"])
            if count:
                summary_row["no_of_records"] = count

            summary_row.pop("unique_records")

        return subcategory_summary

    def default_subcategory_summary(self, subcategory):
        """
        Considered in total taxable value:
            Subcategories for which taxable values and counts are considered in front-end

        Considered in total tax:
            Subcategories for which tax values are considered in front-end

        Indent:
            0: Category
            1: Subcategory
        """
        return {
            "description": subcategory,
            "no_of_records": 0,
            "indent": 1,
            "consider_in_total_taxable_value": (
                False
                if subcategory in SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE
                else True
            ),
            "consider_in_total_tax": (
                False
                if subcategory in SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAX
                else True
            ),
            "unique_records": set(),
            **self.AMOUNT_FIELDS,
        }

    @staticmethod
    def count_doc_issue_summary(summary_row, data_row):
        summary_row["no_of_records"] += data_row.get(
            GSTR1_DataField.TOTAL_COUNT.value, 0
        ) - data_row.get(GSTR1_DataField.CANCELLED_COUNT.value, 0)

    @staticmethod
    def count_hsn_summary(summary_row):
        summary_row["no_of_records"] += 1


class ReconcileGSTR1:
    IGNORED_FIELDS = {GSTR1_DataField.TAX_RATE.value, GSTR1_DataField.DOC_VALUE.value}
    UNREQUIRED_KEYS = {
        GSTR1_DataField.TRANSACTION_TYPE.value,
        GSTR1_DataField.DOC_NUMBER.value,
        GSTR1_DataField.DOC_DATE.value,
        GSTR1_DataField.CUST_GSTIN.value,
        GSTR1_DataField.CUST_NAME.value,
        GSTR1_DataField.REVERSE_CHARGE.value,
    }

    def get_reconcile_gstr1_data(self, gov_data, books_data):
        """
        This function reconciles the data between Books and Gov Data

        Steps:
        1. If already reconciled, return the reconciled data
        2. Update Upload Status for Books Data (if return is not filed)
        3. Reconcile for each subcategory
            - For each row in Books Data, compare with Gov Data
            - For each row in Gov Data (if not in Books Data)
        """
        if self.is_latest_data and self.reconcile:
            reconcile_data = self.get_json_for("reconcile")

            if reconcile_data:
                return reconcile_data

        reconciled_data = {}
        if self.filing_status == "Filed":
            update_books_match = False
        else:
            update_books_match = True

        for subcategory in GSTR1_SubCategory:
            subcategory = subcategory.value
            books_subdata = books_data.get(subcategory) or {}
            gov_subdata = gov_data.get(subcategory) or {}

            if not books_subdata and not gov_subdata:
                continue

            is_list = False  # Object Type for the subdata_value

            reconcile_subdata = {}

            # Books vs Gov
            for key, books_value in books_subdata.items():
                if not reconcile_subdata:
                    is_list = isinstance(books_value, list)

                gov_value = gov_subdata.get(key)

                reconcile_row = self.get_reconciled_row(books_value, gov_value)

                if reconcile_row:
                    reconcile_subdata[key] = reconcile_row

                if not update_books_match:
                    continue

                books_values = books_value if is_list else [books_value]

                # Update each row in Books Data
                for row in books_values:
                    if row.get("upload_status") == "Missing in Books":
                        continue

                    if not gov_value:
                        row["upload_status"] = "Not Uploaded"
                        continue

                    if reconcile_row:
                        row["upload_status"] = "Mismatch"
                    else:
                        row["upload_status"] = "Uploaded"

            # In Gov but not in Books
            for key, gov_value in gov_subdata.items():
                if key in books_subdata:
                    continue

                if not reconcile_subdata:
                    is_list = isinstance(gov_value, list)

                reconcile_subdata[key] = self.get_reconciled_row(None, gov_value)

                if not update_books_match:
                    continue

                books_empty_row = self.get_empty_row(
                    gov_value[0] if is_list else gov_value
                )
                books_empty_row["upload_status"] = "Missing in Books"

                books_subdata[key] = [books_empty_row] if is_list else books_empty_row

            if update_books_match and not books_data.get(subcategory):
                books_data[subcategory] = books_subdata

            if reconcile_subdata:
                reconciled_data[subcategory] = reconcile_subdata

        if update_books_match:
            self.update_json_for("books", books_data)

        self.update_json_for("reconcile", reconciled_data)

        return reconciled_data

    @staticmethod
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
            reconcile_row = ReconcileGSTR1.get_empty_row(
                gov_row[0] if gov_row else books_row[0], ReconcileGSTR1.UNREQUIRED_KEYS
            )
            gov_row = gov_row[0] if gov_row else {}
            books_row = (
                AggregateInvoices.get_aggregate_invoices(books_row) if books_row else {}
            )

        else:
            reconcile_row = ReconcileGSTR1.get_empty_row(gov_row or books_row)
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
            if (
                isinstance(value, (int, float))
                and key not in AggregateInvoices.IGNORED_FIELDS
            ):
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

        reconcile_row["differences"] = ", ".join(reconcile_row["differences"])

        # Return
        if reconcile_row["match_status"] == "Matched":
            return

        reconcile_row["books"] = books_row
        reconcile_row["gov"] = gov_row

        if is_list:
            return [reconcile_row]

        return reconcile_row

    @staticmethod
    def get_empty_row(row: dict, unrequired_keys=None):
        """
        Row with all values as 0
        """
        empty_row = row.copy()

        for key, value in empty_row.items():
            if key in AggregateInvoices.IGNORED_FIELDS:
                continue

            if unrequired_keys and key in unrequired_keys:
                empty_row[key] = None
                continue

            if isinstance(value, (int, float)):
                empty_row[key] = 0

            if key == "items":
                empty_row[key] = [{}]

        return empty_row


class AggregateInvoices:
    IGNORED_FIELDS = {GSTR1_DataField.TAX_RATE.value, GSTR1_DataField.DOC_VALUE.value}

    @staticmethod
    def get_aggregate_data(data: dict):
        """
        Aggregate invoices for each subcategory where required
        and updates the data
        """
        sub_categories_requiring_aggregation = [
            GSTR1_SubCategory.B2CS,
            GSTR1_SubCategory.NIL_EXEMPT,
            GSTR1_SubCategory.AT,
            GSTR1_SubCategory.TXP,
        ]

        aggregate_data = {}

        for subcategory in sub_categories_requiring_aggregation:
            subcategory_data = data.get(subcategory.value)

            if not subcategory_data:
                continue

            aggregate_data[subcategory.value] = (
                AggregateInvoices.get_aggregate_subcategory(subcategory_data)
            )

        return aggregate_data

    @staticmethod
    def get_aggregate_subcategory(subcategory_data: dict):
        value_keys = []
        aggregate_invoices = {}

        for _id, invoices in subcategory_data.items():
            if not value_keys:
                value_keys = AggregateInvoices.get_value_keys(invoices[0])

            aggregate_invoices[_id] = [
                AggregateInvoices.get_aggregate_invoices(invoices, value_keys)
            ]

        return aggregate_invoices

    @staticmethod
    def get_aggregate_invoices(invoices: list, value_keys: list = None) -> dict:
        """
        There can be multiple rows in books data for a single row in gov data
        Aggregate all the rows to a single row
        """
        if not value_keys:
            value_keys = AggregateInvoices.get_value_keys(invoices[0])

        aggregated_invoice = invoices[0].copy()
        aggregated_invoice.update(
            {
                key: sum([invoice.get(key, 0) for invoice in invoices])
                for key in value_keys
            }
        )

        return aggregated_invoice

    @staticmethod
    def get_value_keys(invoice: dict):
        keys = []

        for key, value in invoice.items():
            if not isinstance(value, (int, float)):
                continue

            if key in AggregateInvoices.IGNORED_FIELDS:
                continue

            keys.append(key)

        return keys


class GenerateGSTR1(SummarizeGSTR1, ReconcileGSTR1, AggregateInvoices):
    def generate_gstr1_data(self, filters, callback=None):
        """
        Generate GSTR-1 Data

        Steps:
        1. Check if APIs are enabled. If not, generate only books data.
        2. Get the return status
        3. Get Gov Data
        4. Get Books Data
        5. Reconcile Data
        6. Summarize Data and return
        """
        data = {}

        # APIs Disabled
        if not self.is_gstr1_api_enabled(warn_for_missing_credentials=True):
            return self.generate_only_books_data(data, filters, callback)

        # APIs Enabled
        status = self.get_return_status()

        if status == "Filed":
            gov_data_field = "filed"
        else:
            gov_data_field = "unfiled"

        # Get Data
        gov_data, is_enqueued = self.get_gov_gstr1_data()

        if error_type := gov_data.get("error_type"):
            # otp_requested, invalid_otp

            if error_type == "invalid_otp":
                request_otp(filters.company_gstin)

            data = "otp_requested"
            return callback and callback(data, filters)

        books_data = self.get_books_gstr1_data(filters)

        if is_enqueued:
            return

        reconcile_data = self.get_reconcile_gstr1_data(gov_data, books_data)

        if status != "Filed":
            books_data.update({"aggregate_data": self.get_aggregate_data(books_data)})
            self.update_json_for("books", books_data)

        # Compile Data
        data["status"] = status

        data["reconcile"] = self.normalize_data(reconcile_data)
        data[gov_data_field] = self.normalize_data(gov_data)
        data["books"] = self.normalize_data(books_data)

        self.summarize_data(data)
        return callback and callback(data, filters)

    def generate_only_books_data(self, data, filters, callback=None):
        status = "Not Filed"

        books_data = self.get_books_gstr1_data(filters, aggregate=True)

        data["books"] = self.normalize_data(books_data)
        data["status"] = status

        self.summarize_data(data)
        return callback and callback(data, filters)

    # GET DATA
    def get_gov_gstr1_data(self):
        if self.filing_status == "Filed":
            data_field = "filed"
        else:
            data_field = "unfiled"

        # data exists
        if self.get(data_field):
            mapped_data = self.get_json_for(data_field)

            if mapped_data:
                return mapped_data, False

        # download data
        return download_gstr1_json_data(self)

    def get_books_gstr1_data(self, filters, aggregate=False):
        from india_compliance.gst_india.doctype.gstr_1_beta.gstr_1_beta import (
            get_gstr_1_from_and_to_date,
        )

        # Query / Process / Map / Sumarize / Optionally Save & Return
        data_field = "books"

        # data exists
        if self.is_latest_data and self.get(data_field):
            books_data = self.get_json_for(data_field)

            if books_data:
                return books_data

        from_date, to_date = get_gstr_1_from_and_to_date(
            filters.month_or_quarter, filters.year
        )

        _filters = frappe._dict(
            {
                "company": filters.company,
                "company_gstin": filters.company_gstin,
                "from_date": from_date,
                "to_date": to_date,
            }
        )

        # compute data
        books_data = GSTR1BooksData(_filters).prepare_mapped_data()
        if aggregate:
            books_data.update({"aggregate_data": self.get_aggregate_data(books_data)})

        self.update_json_for(data_field, books_data, reset_reconcile=True)

        return books_data

    # DATA MODIFIERS
    def summarize_data(self, data):
        """
        Summarize data for all fields => reconcile, filed, unfiled, books

        If return status is filed, use summary provided by Govt (usecase: amendments manually updated).
        Else, summarize the data and save it.
        """
        summary_fields = {
            "reconcile": "reconcile_summary",
            "filed": "filed_summary",
            "unfiled": "unfiled_summary",
            "books": "books_summary",
        }

        for key, field in summary_fields.items():
            if not data.get(key):
                continue

            if data.get(field):
                continue

            if self.is_latest_data and self.get(field):
                _data = self.get_json_for(field)

                if _data:
                    data[field] = _data
                    continue

            summary_data = self.get_summarized_data(
                data[key], self.filing_status == "Filed"
            )

            self.update_json_for(field, summary_data)
            data[field] = summary_data

    @staticmethod
    def normalize_data(data):
        """
        Helper function to convert complex objects to simple objects
        Returns object list of rows for each sub-category
        """
        for subcategory, subcategory_data in data.items():
            if subcategory == "aggregate_data":
                data[subcategory] = GenerateGSTR1.normalize_data(subcategory_data)
                continue

            if isinstance(subcategory_data, list | tuple | str):
                continue

            # get first key and value from subcategory_data
            first_value = next(iter(subcategory_data.values()), None)

            if isinstance(first_value, list | tuple):
                # flatten the list of objects
                data[subcategory] = list(itertools.chain(*subcategory_data.values()))

            else:
                data[subcategory] = [*subcategory_data.values()]

        return data


class GSTR1Log(GenerateGSTR1, Document):

    @property
    def status(self):
        return self.generation_status

    def update_status(self, status, commit=False):
        self.db_set("generation_status", status, commit=commit)

    # FILE UTILITY
    def load_data(self, file_field=None):
        data = {}

        if file_field:
            file_fields = [file_field]
        else:
            file_fields = self.get_applicable_file_fields()

        for file_field in file_fields:
            if json_data := self.get_json_for(file_field):
                if "summary" not in file_field:
                    json_data = self.normalize_data(json_data)

                data[file_field] = json_data

        return data

    def get_json_for(self, file_field):
        try:
            if file := get_file_doc(self.doctype, self.name, file_field):
                return get_decompressed_data(file.get_content(encodings=[]))

        except FileNotFoundError:
            # say File not restored
            self.db_set(file_field, None)
            return

    def update_json_for(
        self, file_field, json_data, overwrite=True, reset_reconcile=False
    ):
        if "summary" not in file_field:
            json_data["creation"] = get_datetime_str(get_datetime())
            self.remove_json_for(f"{file_field}_summary")

            # reset reconciled data
            if reset_reconcile:
                self.remove_json_for("reconcile")

        # new file
        if not getattr(self, file_field):
            content = get_compressed_data(json_data)
            file_name = frappe.scrub("{0}-{1}.json.gz".format(self.name, file_field))
            file = frappe.get_doc(
                {
                    "doctype": "File",
                    "attached_to_doctype": self.doctype,
                    "attached_to_name": self.name,
                    "attached_to_field": file_field,
                    "file_name": file_name,
                    "is_private": 1,
                    "content": content,
                }
            ).insert()
            self.db_set(file_field, file.file_url)
            return

        # existing file
        file = get_file_doc(self.doctype, self.name, file_field)

        if overwrite:
            new_json = json_data

        else:
            new_json = get_decompressed_data(file.get_content(encodings=[]))
            new_json.update(json_data)

        content = get_compressed_data(new_json)

        file.save_file(content=content, overwrite=True)
        self.db_set(file_field, file.file_url)

    def remove_json_for(self, file_field):
        if not self.get(file_field):
            return

        file = get_file_doc(self.doctype, self.name, file_field)
        if file:
            file.delete()

        self.db_set(file_field, None)

        if "summary" not in file_field:
            self.remove_json_for(f"{file_field}_summary")

        if file_field == "filed":
            self.remove_json_for("unfiled")

    # GSTR 1 UTILITY
    def is_gstr1_api_enabled(self, settings=None, warn_for_missing_credentials=False):
        if not settings:
            settings = frappe.get_cached_doc("GST Settings")

        if not is_production_api_enabled(settings):
            return False

        if not settings.compare_gstr_1_data:
            return False

        if not settings.has_valid_credentials(self.gstin, "Returns"):
            if warn_for_missing_credentials:
                frappe.publish_realtime(
                    "show_message",
                    dict(
                        message=_(
                            "Credentials are missing for GSTIN {0} for service"
                            " Returns in GST Settings"
                        ).format(self.gstin),
                        title=_("Missing Credentials"),
                    ),
                    user=frappe.session.user,
                )

            return False

        return True

    def is_sek_needed(self, settings=None):
        if not self.is_gstr1_api_enabled(settings):
            return False

        if not self.unfiled or self.filing_status != "Filed":
            return True

        if not self.filed:
            return True

        return False

    def has_all_files(self, settings=None):
        if not self.is_latest_data:
            return False

        file_fields = self.get_applicable_file_fields(settings)
        return all(getattr(self, file_field) for file_field in file_fields)

    def get_return_status(self):
        from india_compliance.gst_india.utils.gstin_info import get_gstr_1_return_status

        status = self.get("filing_status")
        if not status:
            status = get_gstr_1_return_status(
                self.company,
                self.gstin,
                self.return_period,
            )
            self.filing_status = status

        return status

    def get_applicable_file_fields(self, settings=None):
        # Books aggregated data stored in filed (as to file)
        fields = ["books", "books_summary"]

        if self.is_gstr1_api_enabled(settings):
            fields.extend(["reconcile", "reconcile_summary"])

            if self.filing_status == "Filed":
                fields.extend(["filed", "filed_summary"])
            else:
                fields.extend(["unfiled", "unfiled_summary"])

        return fields


def process_gstr_1_returns_info(company, gstin, response):
    return_info = {}

    # compile gstr-1 returns info
    for info in response.get("EFiledlist"):
        if info["rtntype"] == "GSTR1":
            return_info[f"{info['ret_prd']}-{gstin}"] = info

    # existing logs
    gstr1_logs = frappe._dict(
        frappe.get_all(
            "GSTR-1 Log",
            filters={"name": ("in", list(return_info.keys()))},
            fields=["name", "acknowledgement_number"],
            as_list=1,
        )
    )

    # update gstr-1 filed upto
    if frappe.db.exists("GSTIN", gstin):
        gstin_doc = frappe.get_doc("GSTIN", gstin)
    else:
        gstin_doc = frappe.new_doc("GSTIN", gstin=gstin, status="Active")

    def _update_gstr_1_filed_upto(filing_date):
        if not gstin_doc.gstr_1_filed_upto or filing_date > getdate(
            gstin_doc.gstr_1_filed_upto
        ):
            gstin_doc.gstr_1_filed_upto = filing_date
            gstin_doc.save()

    # create or update filed logs
    for key, info in return_info.items():
        filing_details = {
            "filing_status": info["status"],
            "acknowledgement_number": info["arn"],
            "filing_date": datetime.strptime(info["dof"], "%d-%m-%Y").date(),
        }

        filed_upto = get_last_day(
            getdate(f"{info['ret_prd'][2:]}-{info['ret_prd'][0:2]}-01")
        )

        if key in gstr1_logs:
            if gstr1_logs[key] != info["arn"]:
                frappe.db.set_value("GSTR-1 Log", key, filing_details)
                _update_gstr_1_filed_upto(filed_upto)

            # No updates if status is same
            continue

        frappe.get_doc(
            {
                "doctype": "GSTR-1 Log",
                "company": company,
                "gstin": gstin,
                "return_period": info["ret_prd"],
                **filing_details,
            }
        ).insert()
        _update_gstr_1_filed_upto(filed_upto)


def get_file_doc(doctype, docname, attached_to_field):
    try:
        return frappe.get_doc(
            "File",
            {
                "attached_to_doctype": doctype,
                "attached_to_name": docname,
                "attached_to_field": attached_to_field,
            },
        )

    except frappe.DoesNotExistError:
        return None


def get_compressed_data(json_data):
    return gzip.compress(frappe.safe_encode(frappe.as_json(json_data)))


def get_decompressed_data(content):
    return frappe.parse_json(frappe.safe_decode(gzip.decompress(content)))
