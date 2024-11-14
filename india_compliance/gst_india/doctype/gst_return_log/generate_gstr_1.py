# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt
import itertools

import frappe
from frappe import _, unscrub
from frappe.utils import flt

from india_compliance.gst_india.api_classes.taxpayer_returns import GSTR1API
from india_compliance.gst_india.utils.gstr_1 import GovJsonKey, GSTR1_SubCategory
from india_compliance.gst_india.utils.gstr_1.__init__ import (
    CATEGORY_SUB_CATEGORY_MAPPING,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAX,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE,
    GSTR1_Category,
    GSTR1_DataField,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_download import (
    download_gstr1_json_data,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import (
    GSTR1BooksData,
    convert_to_internal_data_format,
    summarize_retsum_data,
)

status_code_map = {
    "P": "Processed",
    "PE": "Processed with Errors",
    "ER": "Error",
    "IP": "In Progress",
}
MAXIMUM_UPLOAD_SIZE = 5200000


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
        summary_row["no_of_records"] += (
            data_row.get(GSTR1_DataField.TOTAL_COUNT.value, 0)
            - data_row.get(GSTR1_DataField.CANCELLED_COUNT.value, 0)
            - data_row.get(GSTR1_DataField.DRAFT_COUNT.value, 0)
        )

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

            # Object Type for the subdata_value
            is_list = self.is_list(books_subdata, gov_subdata)

            self.sanitize_books_data(books_subdata, is_list)

            reconcile_subdata = {}

            # Books vs Gov
            for key, books_value in books_subdata.items():
                gov_value = gov_subdata.get(key)

                reconcile_row = self.get_reconciled_row(books_value, gov_value)

                if reconcile_row:
                    reconcile_subdata[key] = reconcile_row

                if not update_books_match:
                    continue

                books_values = books_value if is_list else [books_value]

                # Update each row in Books Data
                for row in books_values:
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

        self.update_json_for("books", books_data)
        self.update_json_for("reconcile", reconciled_data)

        return reconciled_data

    def sanitize_books_data(self, books_subdata, is_list):
        for key, value in books_subdata.copy().items():
            values = value if is_list else [value]
            if values[0].get("upload_status") == "Missing in Books":
                del books_subdata[key]
                continue

            for row in values:
                row.pop("upload_status", None)

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

    @staticmethod
    def is_list(books_subdata: dict, gov_subdata: dict):
        book_row = next(iter(books_subdata.values()), None)
        gov_row = next(iter(gov_subdata.values()), None)

        return isinstance(book_row or gov_row, list)


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
    def get_gstr1_data(self):
        data = self.load_data()

        if not data:
            return

        data = data
        data["status"] = self.filing_status or "Not Filed"
        if error_data := self.get_json_for("upload_error"):
            data["errors"] = error_data

        data["pending_actions"] = set(
            [
                row.request_type
                for row in self.actions
                if not row.status
                and row.request_type in ["reset", "upload", "proceed_to_file"]
            ]
        )

        self.update_status("Generated")

        return data

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
        return callback and callback(filters)

    def generate_only_books_data(self, data, filters, callback=None):
        status = "Not Filed"

        books_data = self.get_books_gstr1_data(filters, aggregate=True)

        data["books"] = self.normalize_data(books_data)
        data["status"] = status

        self.summarize_data(data)
        return callback and callback(filters)

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


class FileGSTR1:
    def reset_gstr1(self, force):
        verify_request_in_progress(self, force)

        # reset called after proceed to file
        self.db_set({"filing_status": "Not Filed"})

        api = GSTR1API(self)
        response = api.reset_gstr_1_data(self.return_period)

        set_gstr1_actions(self, "reset", response.get("reference_id"), api.request_id)

    def process_reset_gstr1(self):
        if not self.actions:
            return

        api = GSTR1API(self)
        response = None

        doc = self.get_unprocessed_action("reset")

        if not doc:
            return

        response = api.get_return_status(self.return_period, doc.token)

        if response.get("status_cd") != "IP":
            doc.db_set({"status": status_code_map.get(response.get("status_cd"))})
            enqueue_notification(
                self.return_period,
                "reset",
                response.get("status_cd"),
                self.gstin,
            )

        if response.get("status_cd") == "P":
            self.update_json_for("unfiled", {}, reset_reconcile=True)

        return response

    def upload_gstr1(self, json_data, force):
        if not json_data:
            return

        verify_request_in_progress(self, force)

        keys = {category.value for category in GovJsonKey}
        if all(key not in json_data for key in keys):
            frappe.msgprint(_("No data to upload"), indicator="red")
            return

        # upload data after proceed to file
        self.db_set({"filing_status": "Not Filed"})

        # remove error file if it exists
        self.remove_json_for("upload_error")

        # Make API Request
        api = GSTR1API(self)
        response = api.save_gstr_1_data(self.return_period, json_data)

        set_gstr1_actions(self, "upload", response.get("reference_id"), api.request_id)

    def process_upload_gstr1(self):
        if not self.actions:
            return

        api = GSTR1API(self)
        response = None

        doc = self.get_unprocessed_action("upload")

        if not doc:
            return

        response = api.get_return_status(self.return_period, doc.token)
        status_cd = response.get("status_cd")

        if status_cd != "IP":
            doc.db_set({"status": status_code_map.get(status_cd)})
            enqueue_notification(
                self.return_period,
                "upload",
                status_cd,
                self.gstin,
                api.request_id if status_cd == "ER" else None,
            )

        if status_cd == "PE":
            response["error_report"] = convert_to_internal_data_format(
                response.get("error_report"), True
            )
            self.update_json_for("upload_error", response)

        if status_cd == "P":
            self.db_set({"filing_status": "Uploaded"})

            self.update_json_for("unfiled", self.get_json_for("books"))
            self.update_json_for("unfiled_summary", self.get_json_for("books_summary"))

            self.update_json_for("reconcile", {})
            self.update_json_for("reconcile_summary", {})

        return response

    def proceed_to_file_gstr1(self, force):
        verify_request_in_progress(self, force)

        api = GSTR1API(self)
        response = api.proceed_to_file("GSTR1", self.return_period)

        # Return Form already ready to be filed
        if response.error and response.error.error_cd == "RET00003":
            return self.fetch_and_compare_summary(api)

        set_gstr1_actions(
            self, "proceed_to_file", response.get("reference_id"), api.request_id
        )

    def process_proceed_to_file_gstr1(self):
        if not self.actions:
            return

        api = GSTR1API(self)
        response = None

        doc = self.get_unprocessed_action("proceed_to_file")

        if not doc:
            return

        response = api.get_return_status(self.return_period, doc.token)

        if response.get("status_cd") == "IP":
            return response

        doc.db_set({"status": status_code_map.get(response.get("status_cd"))})

        return self.fetch_and_compare_summary(api, response)

    def fetch_and_compare_summary(self, api, response=None):
        if response is None:
            response = {}

        summary = api.get_gstr_1_data("RETSUM", self.return_period)
        if summary.error:
            return

        self.update_json_for("authenticated_summary", summary)

        mapped_summary = self.get_json_for("books_summary")
        gov_summary = convert_to_internal_data_format(summary).get("summary")
        gov_summary = summarize_retsum_data(gov_summary.values())

        differing_categories = get_differing_categories(mapped_summary, gov_summary)

        if not differing_categories:
            self.db_set({"filing_status": "Ready to File"})
            response["filing_status"] = "Ready to File"

        else:
            self.db_set({"filing_status": "Not Filed"})
            response.update(
                {
                    "filing_status": "Not Filed",
                    "differing_categories": differing_categories,
                }
            )
            enqueue_notification(
                self.return_period,
                "proceed_to_file",
                response.get("status_cd"),
                self.gstin,
                api.request_id,
            )

        return response

    def file_gstr1(self, pan, otp, force):
        verify_request_in_progress(self, force)

        summary = self.get_json_for("authenticated_summary")
        api = GSTR1API(self)
        response = api.file_gstr_1(self.return_period, summary, pan, otp)

        # Latest Summary is not available. Please generate summary and try again.
        if response.error and response.error.error_cd == "RET09001":
            self.db_set({"filing_status": "Not Filed"})
            self.update_json_for("authenticated_summary", None)

        if response.get("ack_num"):
            frappe.db.set_value("GSTIN", self.gstin, "last_pan_used_for_gstr", pan)
            self.db_set(
                {
                    "filing_status": "Filed",
                    "filing_date": frappe.utils.nowdate(),
                    "acknowledgement_number": response.get("ack_num"),
                }
            )

            set_gstr1_actions(
                self,
                "file",
                response.get("ack_num"),
                api.request_id,
                status="Processed",
            )

        return response

    def get_amendment_data(self):
        authenticated_summary = convert_to_internal_data_format(
            self.get_json_for("authenticated_summary")
        ).get("summary")
        authenticated_summary = summarize_retsum_data(authenticated_summary.values())

        non_amended_entries = {
            "total_igst_amount": 0,
            "total_cgst_amount": 0,
            "total_sgst_amount": 0,
            "total_cess_amount": 0,
        }
        amended_liability = {}

        for data in authenticated_summary:
            if "Net Liability from Amendments" == data["description"]:
                amended_liability = data
            elif data.get("consider_in_total_taxable_value") or data.get(
                "consider_in_total_tax"
            ):
                for key, value in data.items():
                    if key not in non_amended_entries:
                        continue

                    non_amended_entries[key] += value

        return {
            "non_amended_liability": non_amended_entries,
            "amended_liability": amended_liability,
        }


def verify_request_in_progress(return_log, force):
    for row in return_log.actions:
        if row.status:
            continue

        if force:
            row.db_set({"status": "Ignored"})
            continue

        frappe.throw(
            _(
                "There is a {0} request in progress. Please wait for the process to complete."
            ).format(row.request_type)
        )


def get_differing_categories(mapped_summary, gov_summary):
    KEYS_TO_COMPARE = {
        "total_cess_amount",
        "total_cgst_amount",
        "total_igst_amount",
        "total_sgst_amount",
        "total_taxable_value",
    }

    # TODO: Check this for all categories
    CATEGORY_KEYS = {
        (GSTR1_Category.NIL_EXEMPT.value): {
            "total_exempted_amount",
            "total_nil_rated_amount",
            "total_non_gst_amount",
        },
        (GSTR1_Category.DOC_ISSUE.value): {
            "no_of_records",
        },
    }

    IGNORED_CATEGORIES = {"Net Liability from Amendments"}

    gov_summary = {row["description"]: row for row in gov_summary if row["indent"] == 0}
    compared_categories = set()
    differing_categories = set()

    # This will intentionally skip the row in govt_summary with amended data
    for row in mapped_summary:
        if row["indent"] != 0:
            continue

        category = row["description"]
        if category in IGNORED_CATEGORIES:
            continue

        compared_categories.add(category)
        gov_entry = gov_summary.get(category, {})

        keys_to_compare = CATEGORY_KEYS.get(category, KEYS_TO_COMPARE)

        for key in keys_to_compare:
            if gov_entry.get(key, 0) != row.get(key):
                differing_categories.add(category)
                break

    for row in gov_summary.values():
        # Amendments are with indent 1. Hence auto-skipped
        category = row["description"]
        if category in IGNORED_CATEGORIES:
            continue

        if category in compared_categories:
            continue

        keys_to_compare = CATEGORY_KEYS.get(row["description"], KEYS_TO_COMPARE)

        for key in keys_to_compare:
            if row.get(key, 0) != 0:
                differing_categories.add(row["description"])
                break

    return differing_categories


def set_gstr1_actions(doc, request_type, token, request_id, status=None):
    if not token:
        return

    row = {
        "request_type": request_type,
        "token": token,
        "creation_time": frappe.utils.now_datetime(),
    }

    if status:
        row["status"] = status

    doc.append("actions", row)
    doc.save()
    enqueue_link_integration_request(token, request_id)


def enqueue_link_integration_request(token, request_id):
    """
    Integration request is enqueued. Hence, it's name is not available immediately.
    Hence, link it after the request is processed.
    """
    frappe.enqueue(
        link_integration_request, queue="long", token=token, request_id=request_id
    )


def link_integration_request(token, request_id):
    doc_name = frappe.db.get_value("Integration Request", {"request_id": request_id})
    if doc_name:
        frappe.db.set_value(
            "GSTR Action", {"token": token}, {"integration_request": doc_name}
        )


def enqueue_notification(
    return_period, request_type, status_cd, gstin, request_id=None
):
    frappe.enqueue(
        create_notification,
        queue="long",
        return_period=return_period,
        request_type=request_type,
        status_cd=status_cd,
        gstin=gstin,
        request_id=request_id,
    )


def create_notification(return_period, request_type, status_cd, gstin, request_id=None):
    # request_id shows failure response
    status_message_map = {
        "P": f"Data {request_type} for GSTIN {gstin} and return period {return_period} has been successfully completed.",
        "PE": f"Data {request_type} for GSTIN {gstin} and return period {return_period} is completed with errors",
        "ER": f"Data {request_type} for GSTIN {gstin} and return period {return_period} has encountered errors",
    }

    if request_id and (
        doc_name := frappe.db.get_value(
            "Integration Request", {"request_id": request_id}
        )
    ):
        document_type = "Integration Request"
        document_name = doc_name
    else:
        document_type = document_name = "GSTR-1 Beta"

    notification = frappe.get_doc(
        {
            "doctype": "Notification Log",
            "for_user": frappe.session.user,
            "type": "Alert",
            "document_type": document_type,
            "document_name": document_name,
            "subject": f"Data {request_type} for GSTIN {gstin} and return period {return_period}",
            "email_content": status_message_map.get(status_cd),
        }
    )
    notification.insert()
