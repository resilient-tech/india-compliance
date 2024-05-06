# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt
import gzip
import itertools
from datetime import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, flt, get_datetime, getdate, get_last_day

from india_compliance.gst_india.utils.gstr_1 import GSTR1_SubCategories
from india_compliance.gst_india.utils.gstr_1.__init__ import (
    CATEGORY_SUB_CATEGORY_MAPPING,
    GSTR1_DataFields,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAX,
)

DOCTYPE = "GSTR-1 Filed Log"


class GSTR1FiledLog(Document):

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
        if file := get_file_doc(self.name, file_field):
            return get_decompressed_data(file.get_content())

    def update_json_for(self, file_field, json_data, overwrite=True):
        if file_field == "books":
            self.db_set("computed_on", get_datetime())

        # new file
        if not getattr(self, file_field):
            content = get_compressed_data(json_data)
            file_name = frappe.scrub("{0}-{1}.json.gz".format(self.name, file_field))
            file = frappe.get_doc(
                {
                    "doctype": "File",
                    "attached_to_doctype": DOCTYPE,
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
        file = get_file_doc(self.name, file_field)

        # reset summary
        if "summary" not in file_field:
            self.remove_json_for(f"{file_field}_summary")

        if overwrite:
            new_json = json_data

            # reset reconciled data
            if file_field in ("books", "filed", "unfiled"):
                self.remove_json_for("reconcile")

        else:
            new_json = get_decompressed_data(file.get_content())
            new_json.update(json_data)

        content = get_compressed_data(new_json)

        file.save_file(content=content, overwrite=True)
        self.db_set(file_field, file.file_url)

    def remove_json_for(self, file_field):
        if not self.get(file_field):
            return

        get_file_doc(self.name, file_field).delete()
        self.db_set(file_field, None)

        if "summary" not in file_field:
            self.remove_json_for(f"{file_field}_summary")

    # DATA MODIFIERS
    def normalize_data(self, data):
        """
        Helper function to convert complex objects to simple objects
        Returns object list of rows for each sub-category
        """
        for subcategory, subcategory_data in data.items():
            if isinstance(subcategory_data, list | tuple):
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

    # GSTR 1 UTILITY
    def is_sek_needed(self, settings=None):
        if not settings:
            settings = frappe.get_cached_doc("GST Settings")

        if not settings.analyze_filed_data:
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

    def get_applicable_file_fields(self, settings=None):
        if not settings:
            settings = frappe.get_cached_doc("GST Settings")

        fields = ["books", "books_summary"]

        if settings.analyze_filed_data:
            fields.extend(["reconcile", "reconcile_summary"])

            if self.filing_status == "Filed":
                fields.extend(["filed", "filed_summary"])
            else:
                fields.extend(["unfiled", "unfiled_summary"])

        return fields


def summarize_data(data, for_books=False):
    """
    Helper function to summarize data for each sub-category
    """
    subcategory_summary = {}
    AMOUNT_FIELDS = {
        "total_taxable_value": 0,
        "total_igst_amount": 0,
        "total_cgst_amount": 0,
        "total_sgst_amount": 0,
        "total_cess_amount": 0,
    }

    # Sub-category wise
    for subcategory in GSTR1_SubCategories:
        subcategory = subcategory.value
        if subcategory not in data:
            continue

        summary_row = subcategory_summary.setdefault(
            subcategory,
            {
                "description": subcategory,
                "no_of_records": 0,
                "indent": 1,
                "consider_in_total_taxable_value": (
                    False
                    if subcategory
                    in SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE
                    else True
                ),
                "consider_in_total_tax": (
                    False
                    if subcategory in SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAX
                    else True
                ),
                "unique_records": set(),
                **AMOUNT_FIELDS,
            },
        )

        _data = data[subcategory]
        for row in _data:
            if row.get("upload_status") == "Missing in Books":
                continue

            for key in AMOUNT_FIELDS:
                summary_row[key] += row.get(key, 0)

            if doc_num := row.get("document_number"):
                summary_row["unique_records"].add(doc_num)

            if subcategory == GSTR1_SubCategories.DOC_ISSUE.value:
                count_doc_issue_summary(summary_row, row)

            if subcategory == GSTR1_SubCategories.HSN.value:
                count_hsn_summary(summary_row)

    for subcategory in subcategory_summary.keys():
        summary_row = subcategory_summary[subcategory]
        count = len(summary_row["unique_records"])
        if count:
            summary_row["no_of_records"] = count

        summary_row.pop("unique_records")

    # Category wise
    cateogory_summary = []
    for category, sub_categories in CATEGORY_SUB_CATEGORY_MAPPING.items():
        # Init category row
        category = category.value
        summary_row = {
            "description": category,
            "no_of_records": 0,
            "indent": 0,
            **AMOUNT_FIELDS,
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

            for key in AMOUNT_FIELDS:
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


def count_doc_issue_summary(summary_row, data_row):
    summary_row["no_of_records"] += data_row.get(
        GSTR1_DataFields.TOTAL_COUNT.value, 0
    ) - data_row.get(GSTR1_DataFields.CANCELLED_COUNT.value, 0)


def count_hsn_summary(summary_row):
    summary_row["no_of_records"] += 1


def process_gstr_1_returns_info(gstin, response):
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
            fields=["name", "filing_status"],
            as_list=1,
        )
    )

    existing_gstr_1_filed_upto = frappe.get_cached_value(
        "GST Settings", None, "gstr_1_filed_upto"
    )

    def _update_gstr_1_filed_upto(filing_date):
        if not existing_gstr_1_filed_upto or filing_date > existing_gstr_1_filed_upto:
            frappe.db.set_value("GST Settings", None, "gstr_1_filed_upto", filing_date)

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
            if filed_logs[key] != info["status"]:
                frappe.db.set_value("GSTR-1 Filed Log", key, filing_details)
                _update_gstr_1_filed_upto(filed_upto)

            # No updates if status is same
            continue

        frappe.get_doc(
            {
                "doctype": "GSTR-1 Filed Log",
                "gstin": gstin,
                "return_period": info["ret_prd"],
                **filing_details,
            }
        ).insert()
        _update_gstr_1_filed_upto(filed_upto)


def get_file_doc(gstr1_log_name, attached_to_field):
    try:
        return frappe.get_doc(
            "File",
            {
                "attached_to_doctype": DOCTYPE,
                "attached_to_name": gstr1_log_name,
                "attached_to_field": attached_to_field,
            },
        )

    except frappe.DoesNotExistError:
        return None


def get_compressed_data(json_data):
    return gzip.compress(frappe.safe_encode(frappe.as_json(json_data)))


def get_decompressed_data(content):
    return frappe.parse_json(frappe.safe_decode(gzip.decompress(content)))
