# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt
import gzip
import itertools
from datetime import datetime

import frappe
from frappe import _, unscrub
from frappe.model.document import Document
from frappe.utils import (
    add_to_date,
    flt,
    get_datetime,
    get_datetime_str,
    get_last_day,
    getdate,
)

from india_compliance.gst_india.utils import is_production_api_enabled
from india_compliance.gst_india.utils.gstr_1 import GSTR1_SubCategories
from india_compliance.gst_india.utils.gstr_1.__init__ import (
    CATEGORY_SUB_CATEGORY_MAPPING,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAX,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE,
    GSTR1_DataFields,
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
        if is_filed:
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

        for subcategory in GSTR1_SubCategories:
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

                elif subcategory == GSTR1_SubCategories.DOC_ISSUE.value:
                    self.count_doc_issue_summary(summary_row, row)

                elif subcategory == GSTR1_SubCategories.HSN.value:
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

    def count_doc_issue_summary(self, summary_row, data_row):
        summary_row["no_of_records"] += data_row.get(
            GSTR1_DataFields.TOTAL_COUNT.value, 0
        ) - data_row.get(GSTR1_DataFields.CANCELLED_COUNT.value, 0)

    def count_hsn_summary(self, summary_row):
        summary_row["no_of_records"] += 1


class ReconcileGSTR1:
    def get_reconcile_gstr1_data(self, gov_data, books_data):
        # Everything from gov_data compared with books_data
        # Missing in gov_data
        # Update books data (optionally if not filed)
        # Prepare data / Sumarize / Save & Return / Optionally save books data
        if self.is_latest_data and self.reconcile:
            return self.get_json_for("reconcile")

        reconciled_data = {}
        if self.filing_status == "Filed":
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
                reconcile_row = self.get_reconciled_row(books_value, gov_value)

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

                reconcile_subdata[key] = self.get_reconciled_row(None, gov_value)

                if not update_books_match or ignore_upload_status:
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

    def get_reconciled_row(self, books_row, gov_row):
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
            reconcile_row = self.get_empty_row(gov_row[0] if gov_row else books_row[0])
            gov_row = gov_row[0] if gov_row else {}
            books_row = self.get_aggregated_row(books_row) if books_row else {}

        else:
            reconcile_row = self.get_empty_row(gov_row or books_row)
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

    @staticmethod
    def get_empty_row(row: dict):
        """
        Row with all values as 0
        """
        empty_row = row.copy()

        for key, value in empty_row.items():
            if isinstance(value, (int, float)):
                empty_row[key] = 0

        return empty_row

    @staticmethod
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


class GenerateGSTR1(SummarizeGSTR1, ReconcileGSTR1):
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
        if not self.is_gstr1_api_enabled():
            self.generate_only_books_data(data, filters, callback)
            return

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
            callback and callback(data, filters)
            return

        books_data = self.get_books_gstr1_data(filters)

        if is_enqueued:
            return

        reconcile_data = self.get_reconcile_gstr1_data(gov_data, books_data)

        # Compile Data
        data["status"] = status

        data["reconcile"] = self.normalize_data(reconcile_data)
        data[gov_data_field] = self.normalize_data(gov_data)
        data["books"] = self.normalize_data(books_data)

        self.summarize_data(data, gov_data_field)
        callback and callback(data, filters)

    def generate_only_books_data(self, data, filters, callback=None):
        books_data = self.get_books_gstr1_data(filters)

        data["status"] = "Not Filed"
        data["books"] = self.normalize_data(books_data)

        self.summarize_data(data)
        callback and callback(data, filters)

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

    def get_books_gstr1_data(self, filters):
        from india_compliance.gst_india.doctype.gstr_1_beta.gstr_1_beta import (
            get_gstr_1_from_and_to_date,
        )

        # Query / Process / Map / Sumarize / Optionally Save & Return
        data_field = "books"

        # data exists
        if self.is_latest_data and self.get(data_field):
            mapped_data = self.get_json_for(data_field)

            if mapped_data:
                return mapped_data

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
        mapped_data = GSTR1BooksData(_filters).prepare_mapped_data()
        self.update_json_for(data_field, mapped_data)

        return mapped_data

    # DATA MODIFIERS
    def summarize_data(self, data, gov_data_field=None):
        """
        Summarize data for all fields => reconcile, gov_data_field, books

        If gov data is filed, use summary provided by Govt (usecase: amendments manually updated).
        Else, summarize the data and save it.
        """
        summary_fields = {
            "reconcile": "reconcile_summary",
            f"{gov_data_field}": f"{gov_data_field}_summary",
            "books": "books_summary",
        }

        for key, field in summary_fields.items():
            if not data.get(key):
                continue

            if self.is_latest_data and self.get(field):
                data[field] = self.get_json_for(field)
                continue

            summary_data = self.get_summarized_data(data[key], key == "filed")

            self.update_json_for(field, summary_data)
            data[field] = summary_data

    def normalize_data(self, data):
        """
        Helper function to convert complex objects to simple objects
        Returns object list of rows for each sub-category
        """
        for subcategory, subcategory_data in data.items():
            if isinstance(subcategory_data, list | tuple | str):
                data[subcategory] = subcategory_data
                continue

            # get first key and value from subcategory_data
            first_value = next(iter(subcategory_data.values()), None)

            if isinstance(first_value, list | tuple):
                # flatten the list of objects
                data[subcategory] = list(itertools.chain(*subcategory_data.values()))

            else:
                data[subcategory] = [*subcategory_data.values()]

        return data


class GSTR1FiledLog(GenerateGSTR1, Document):

    @property
    def status(self):
        return self.generation_status

    def update_status(self, status, commit=False):
        self.db_set("generation_status", status, commit=commit)

    def show_report(self):
        # TODO: Implement
        pass

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
        if file := get_file_doc(self.doctype, self.name, file_field):
            return get_decompressed_data(file.get_content())

    def update_json_for(self, file_field, json_data, overwrite=True):
        if "summary" not in file_field:
            json_data["creation"] = get_datetime_str(get_datetime())
            self.remove_json_for(f"{file_field}_summary")

        # reset reconciled data
        if overwrite and file_field in ("books", "filed", "unfiled"):
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
            new_json = get_decompressed_data(file.get_content())
            new_json.update(json_data)

        content = get_compressed_data(new_json)

        file.save_file(content=content, overwrite=True)
        self.db_set(file_field, file.file_url)

    def remove_json_for(self, file_field):
        if not self.get(file_field):
            return

        get_file_doc(self.doctype, self.name, file_field).delete()
        self.db_set(file_field, None)

        if "summary" not in file_field:
            self.remove_json_for(f"{file_field}_summary")

    # GSTR 1 UTILITY
    def is_gstr1_api_enabled(self, settings=None):
        if not settings:
            settings = frappe.get_cached_doc("GST Settings")

        return is_production_api_enabled(settings) and settings.analyze_filed_data

    def is_sek_needed(self, settings=None):
        if not self.is_gstr1_api_enabled(settings):
            return False

        if not self.unfiled or self.filing_status != "Filed":
            return True

        if not self.filed:
            return True

        return False

    def is_sek_valid(self, settings=None):
        if not settings:
            settings = frappe.get_cached_doc("GST Settings")

        for credential in settings.credentials:
            if credential.service == "Returns" and credential.gstin == self.gstin:
                break

        else:
            frappe.throw(
                _("No credential found for the GSTIN {0} in the GST Settings").format(
                    self.gstin
                )
            )

        if credential.session_expiry and credential.session_expiry > add_to_date(
            None, minutes=-30
        ):
            return True

    def has_all_files(self, settings=None):
        if not self.is_latest_data:
            return False

        file_fields = self.get_applicable_file_fields(settings)
        return all(getattr(self, file_field) for file_field in file_fields)

    def get_return_status(self):
        from india_compliance.gst_india.utils.gstin_info import get_gstr_1_return_status

        status = self.filing_status
        if not status:
            status = get_gstr_1_return_status(
                self.company,
                self.gstin,
                self.return_period,
            )
            self.filing_status = status

        return status

    def get_applicable_file_fields(self, settings=None):
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

    # existing filed logs
    filed_logs = frappe._dict(
        frappe.get_all(
            "GSTR-1 Filed Log",
            filters={"name": ("in", list(return_info.keys()))},
            fields=["name", "acknowledgement_number"],
            as_list=1,
        )
    )

    # update gstr-1 filed upto
    gstin_doc = frappe.get_doc("GSTIN", gstin)
    if not gstin_doc:
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

        if key in filed_logs:
            if filed_logs[key] != info["arn"]:
                frappe.db.set_value("GSTR-1 Filed Log", key, filing_details)
                _update_gstr_1_filed_upto(filed_upto)

            # No updates if status is same
            continue

        frappe.get_doc(
            {
                "doctype": "GSTR-1 Filed Log",
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
