# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt
import gzip
from datetime import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date

DOCTYPE = "GSTR-1 Filed Log"


class GSTR1FiledLog(Document):

    def show_report(self):
        # TODO: Implement
        pass

    def load_data(self):
        pass

    def is_sek_needed(self, settings=None):
        if not settings:
            settings = frappe.get_cached_doc("GST Settings")

        if not settings.analyze_filed_data:
            return False

        if not self.e_invoice_data or self.filing_status != "Filed":
            return True

        if not self.filed_gstr1:
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
        if not settings:
            settings = frappe.get_cached_doc("GST Settings")

        if not self.is_latest_data:
            return False

        files = [
            "computed_gstr1",
            "computed_gstr1_summary",
        ]

        if settings.analyze_filed_data:
            files.extend(["reconciled_gstr1", "reconciled_gstr1_summary"])

            if self.filing_status == "Filed":
                files.extend(["filed_gstr1", "filed_gstr1_summary"])
            else:
                files.extend(["e_invoice_data", "e_invoice_summary"])

        return all(getattr(self, file) for file in files)


def process_gstr_1_returns_info(gstin, response):
    return_info = {}

    for info in response.get("EFiledlist"):
        if info["rtntype"] == "GSTR1":
            return_info[f"{info['ret_prd']}-{gstin}"] = info

    filed_logs = frappe._dict(
        frappe.get_all(
            "GSTR-1 Filed Log",
            filters={"name": ("in", list(return_info.keys()))},
            fields=["name", "filing_status"],
            as_list=1,
        )
    )

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


def create_gstr1_filed_log(
    gstin,
    return_period,
    gstr_1_log_type,
    json_data,
    returns_data=None,
):
    if gstr_1_filed_log := frappe.db.exists(
        DOCTYPE, {"gstin": gstin, "return_period": return_period}
    ):
        gstr_1_filed_log = frappe.get_doc(DOCTYPE, gstr_1_filed_log)
    else:
        gstr_1_filed_log = frappe.new_doc(DOCTYPE)
        gstr_1_filed_log.update({"gstin": gstin, "return_period": return_period}).save()

    file = create_log_file(
        gstin, gstr_1_log_type, return_period, json_data, gstr_1_filed_log
    )

    gstr_1_filed_log.update({gstr_1_log_type: file.file_url})

    if returns_data:
        gstr_1_filed_log.update(
            {
                "filing_status": returns_data["status"],
                "acknowledgement_number": returns_data["arn"],
                "filing_date": datetime.strptime(
                    returns_data["dof"], "%d-%m-%Y"
                ).date(),
            }
        )

    gstr_1_filed_log.save()


def get_gstr1_data(gstin, return_period, log_types):
    gstr1_filed_log_docname = get_gstr1_filed_log_doc(gstin, return_period)

    if not gstr1_filed_log_docname:
        return

    if files := get_file_doc(gstr1_filed_log_docname, log_types):
        return {file: get_decompressed_data(files[file]) for file in files}


def get_gstr1_filed_log_doc(gstin, return_period):
    gstr1_filed_log = frappe.get_all(
        DOCTYPE,
        fields=["name"],
        filters={"gstin": gstin, "return_period": return_period},
        pluck="name",
    )

    return gstr1_filed_log[0] if gstr1_filed_log else None


def create_log_file(gstin, gstr_1_log_type, return_period, json_data, gstr_1_filed_log):
    file_name = frappe.scrub(
        "{0} {1} {2}.json.gz".format(gstin, gstr_1_log_type, return_period)
    )
    compressed_data = get_compressed_data(json_data)

    if file := get_file_doc(gstr_1_filed_log.name, [gstr_1_log_type]):
        file.save_file(content=compressed_data, overwrite=True)
    else:
        file = frappe.new_doc("File")
        file.update(
            {
                "attached_to_name": gstr_1_filed_log.name,
                "attached_to_doctype": DOCTYPE,
                "attached_to_field": gstr_1_log_type,
                "file_name": file_name,
                "is_private": 1,
                "content": compressed_data,
            }
        ).save()

    return file


def get_file_doc(docname, log_types):
    files = frappe.get_all(
        "File",
        fields=["name", "attached_to_field"],
        filters={
            "attached_to_doctype": DOCTYPE,
            "attached_to_name": docname,
            "attached_to_field": ["in", log_types],
        },
    )

    if len(log_types) == 1:
        return frappe.get_doc("File", files[0].name) if files else None

    return {file.attached_to_field: frappe.get_doc("File", file) for file in files}


def get_compressed_data(json_data):
    return gzip.compress(frappe.safe_encode(frappe.as_json(json_data)))


def get_decompressed_data(file):
    return frappe.parse_json(frappe.safe_decode(gzip.decompress(file.get_content())))
