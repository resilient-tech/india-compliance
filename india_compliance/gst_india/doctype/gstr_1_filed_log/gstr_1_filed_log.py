# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt
import gzip
import itertools
from datetime import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, get_datetime

from india_compliance.gst_india.utils.gstr_1 import GSTR1_SubCategories
from india_compliance.gst_india.utils.gstr_1.__init__ import (
    CATEGORY_SUB_CATEGORY_MAPPING,
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
    def load_data(self):
        data = {}
        file_fields = self.get_applicable_file_fields()

        for file_field in file_fields:
            if json_data := self.get_json_for(file_field):
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
            if file_field in ["books", "filed"]:
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

        if not self.e_invoice or self.filing_status != "Filed":
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
                fields.extend(["e_invoice", "e_invoice_summary"])

        return fields

    def summarize_filed_data(self):
        summary_data = {}
        gov_summary_data = self.get_json_for("filed_summary")

        for category, value in gov_summary_data.items():
            gov_summary_data[category]["indent"] = 1
            summary_data[category] = value

        for category in CATEGORY_SUB_CATEGORY_MAPPING:
            category_dict = {}
            category_dict["indent"] = 0
            category_dict["description"] = category.value
            category_dict["no_of_records"] = 0
            category_dict["total_cess_amount"] = 0
            category_dict["total_cgst_amount"] = 0
            category_dict["total_sgst_amount"] = 0
            category_dict["total_igst_amount"] = 0
            category_dict["total_taxable_value"] = 0
            for subcategory in CATEGORY_SUB_CATEGORY_MAPPING[category]:
                if summary_data.get(subcategory.value):
                    no_of_records = summary_data[subcategory.value]["no_of_records"]
                    no_of_records = int(no_of_records) if no_of_records != "" else 0

                    category_dict["no_of_records"] += no_of_records
                    category_dict["total_cess_amount"] += summary_data[
                        subcategory.value
                    ]["total_cess_amount"]
                    category_dict["total_cgst_amount"] += summary_data[
                        subcategory.value
                    ]["total_cgst_amount"]
                    category_dict["total_sgst_amount"] += summary_data[
                        subcategory.value
                    ]["total_sgst_amount"]
                    category_dict["total_igst_amount"] += summary_data[
                        subcategory.value
                    ]["total_igst_amount"]
                    category_dict["total_taxable_value"] += summary_data[
                        subcategory.value
                    ]["total_taxable_value"]
            if category_dict["no_of_records"]:
                summary_data[category.value] = category_dict

        return summary_data


def summarize_data(data, for_books=False):
    """
    Helper function to summarize data for each sub-category
    """

    # Docs Count
    # for Docs summary: Differently

    # For Books:
    # AT & TXP & HSN

    # For Other than books:
    # Nil, B2Cs, AT, TXP, HSN

    summary = {}
    AMOUNT_FIELDS = {
        "total_taxable_value": 0,
        "total_igst_amount": 0,
        "total_cgst_amount": 0,
        "total_sgst_amount": 0,
        "total_cess_amount": 0,
    }

    for category in GSTR1_SubCategories:
        category = category.value
        summary[category] = {
            "description": category,
            "no_of_records": "",
            "indent": 1,
            "unique_records": set(),
            **AMOUNT_FIELDS,
        }

    for category, _data in data.items():
        summary_row = summary[category]

        for row in _data:
            for key in AMOUNT_FIELDS:
                summary_row[key] += row.get(key, 0)

            if doc_num := row.get("document_number"):
                summary_row["unique_records"].add(doc_num)

    for category in summary.copy().keys():
        summary_row = summary[category]
        count = len(summary_row["unique_records"])
        if count:
            summary_row["no_of_records"] = count

        if sum(summary_row[field] for field in AMOUNT_FIELDS) == 0:
            del summary[category]
            continue

        summary_row.pop("unique_records")

    # Category wise
    final_summary = {}
    for category in CATEGORY_SUB_CATEGORY_MAPPING:
        final_summary[category.value] = {}

    # TODO: Implement
    return summary


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

    # create or update filed logs
    for key, info in return_info.items():
        filing_details = {
            "filing_status": info["status"],
            "acknowledgement_number": info["arn"],
            "filing_date": datetime.strptime(info["dof"], "%d-%m-%Y").date(),
        }

        if key in filed_logs:
            if filed_logs[key] != info["status"]:
                frappe.db.set_value("GSTR-1 Filed Log", key, filing_details)

            continue

        frappe.get_doc(
            {
                "doctype": "GSTR-1 Filed Log",
                "gstin": gstin,
                "return_period": info["ret_prd"],
                **filing_details,
            }
        ).insert()


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
