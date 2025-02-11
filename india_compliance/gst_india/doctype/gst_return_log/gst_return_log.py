# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import gzip
from datetime import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
    get_datetime,
    get_datetime_str,
    get_last_day,
    get_link_to_form,
    getdate,
)

from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    FileGSTR1,
    GenerateGSTR1,
)
from india_compliance.gst_india.utils import (
    get_party_for_gstin,
    is_production_api_enabled,
)

DOCTYPE = "GST Return Log"


class GSTReturnLog(GenerateGSTR1, FileGSTR1, Document):
    @property
    def status(self):
        return self.generation_status

    def update_status(self, status, commit=False):
        self.db_set("generation_status", status, commit=commit)

    # FILE UTILITY
    def load_data(self, *file_field):
        data = {}

        if file_field:
            file_fields = list(file_field)
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

        if not settings.enable_gstr_1_api:
            return False

        if not settings.has_valid_credentials(self.gstin, "Returns"):
            if warn_for_missing_credentials:
                frappe.publish_realtime(
                    "show_missing_gst_credentials_message",
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
            self.db_set("filing_status", status)

        return status

    def get_applicable_file_fields(self, settings=None):
        # Books aggregated data stored in filed (as to file)
        if not settings:
            settings = frappe.get_cached_doc("GST Settings")

        fields = ["books", "books_summary"]

        if self.is_gstr1_api_enabled(settings):
            if self.filing_status == "Filed":
                fields.extend(
                    ["reconcile", "reconcile_summary", "filed", "filed_summary"]
                )
            elif settings.compare_unfiled_data:
                fields.extend(
                    ["reconcile", "reconcile_summary", "unfiled", "unfiled_summary"]
                )

        return fields

    def get_unprocessed_action(self, action):
        for row in self.get("actions") or []:
            if row.request_type == action and not row.status:
                return row


@frappe.whitelist()
def download_file():
    frappe.has_permission("GST Return Log", "read")

    data = frappe._dict(frappe.local.form_dict)
    frappe.response["filename"] = data["file_name"]

    file = get_file_doc(data["doctype"], data["name"], data["file_field"])
    frappe.response["filecontent"] = file.get_content(encodings=[])

    frappe.response["type"] = "download"


def process_gstr_returns_info(company, gstin, e_filed_list):
    process_gstr_1_returns_info(company, gstin, e_filed_list)
    process_gstr_3b_returns_info(company, gstin, e_filed_list)


def process_gstr_1_returns_info(company, gstin, e_filed_list):
    return_info = {}

    # compile gstr-1 returns info
    for info in e_filed_list:
        if info["rtntype"] == "GSTR1":
            return_info[f"GSTR1-{info['ret_prd']}-{gstin}"] = info

    # existing logs
    gstr1_logs = frappe._dict(
        frappe.get_all(
            DOCTYPE,
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
            gstin_doc.save(ignore_permissions=True)

    # create or update filed logs
    for key, info in return_info.items():
        filing_details = {
            "return_type": "GSTR1",
            "filing_status": info["status"],
            "acknowledgement_number": info["arn"],
            "filing_date": datetime.strptime(info["dof"], "%d-%m-%Y").date(),
        }

        filed_upto = get_last_day(
            getdate(f"{info['ret_prd'][2:]}-{info['ret_prd'][0:2]}-01")
        )

        if key in gstr1_logs:
            if gstr1_logs[key] != info["arn"]:
                frappe.db.set_value(DOCTYPE, key, filing_details)
                _update_gstr_1_filed_upto(filed_upto)

            # No updates if status is same
            continue

        frappe.get_doc(
            {
                "doctype": DOCTYPE,
                "company": company,
                "gstin": gstin,
                "return_period": info["ret_prd"],
                **filing_details,
            }
        ).insert()
        _update_gstr_1_filed_upto(filed_upto)


def process_gstr_3b_returns_info(company, gstin, e_filed_list):
    for info in e_filed_list:
        if info["status"] != "Filed":
            continue

        if frappe.db.exists(
            "GST Return Log",
            f'GSTR3B-{info["ret_prd"]}-{gstin}',
        ):
            continue

        gstr3b_log = frappe.new_doc("GST Return Log")
        gstr3b_log.return_period = info["ret_prd"]
        gstr3b_log.company = company
        gstr3b_log.gstin = gstin
        gstr3b_log.return_type = "GSTR3B"
        gstr3b_log.filing_status = "Filed"
        gstr3b_log.acknowledgement_number = info["arn"]
        gstr3b_log.filing_date = datetime.strptime(info["dof"], "%d-%m-%Y").date()
        gstr3b_log.insert()


def get_gst_return_log(posting_date, company_gstin):
    period = getdate(posting_date).strftime("%m%Y")
    if name := frappe.db.exists(DOCTYPE, f"GSTR1-{period}-{company_gstin}"):
        return frappe.get_doc(DOCTYPE, name)


def add_comment_to_gst_return_log(doc, action):
    if not (log := get_gst_return_log(doc.posting_date, doc.company_gstin)):
        return

    log.add_comment(
        "Comment",
        f"{doc.doctype} : {get_link_to_form(doc.doctype, doc.name)} has been {action} by {frappe.session.user}",
    )


def update_is_not_latest_gstr1_data(posting_date, company_gstin):
    period = posting_date.strftime("%m%Y")

    frappe.db.set_value(
        "GST Return Log", f"GSTR1-{period}-{company_gstin}", "is_latest_data", 0
    )

    frappe.publish_realtime(
        "is_not_latest_gstr1_data",
        message={"filters": {"company_gstin": company_gstin, "period": period}},
        doctype="GSTR-1 Beta",
        docname="GSTR-1 Beta",
    )


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
        frappe.clear_last_message()
        return None


def get_compressed_data(json_data):
    return gzip.compress(frappe.safe_encode(frappe.as_json(json_data)))


def get_decompressed_data(content):
    return frappe.parse_json(frappe.safe_decode(gzip.decompress(content)))


def create_ims_return_log(company_gstin):
    company = get_party_for_gstin(company_gstin, "Company")

    if frappe.db.exists("GST Return Log", f"IMS-ALL-{company_gstin}"):
        return

    ims_log = frappe.new_doc("GST Return Log")
    ims_log.return_period = "ALL"
    ims_log.company = company
    ims_log.gstin = company_gstin
    ims_log.return_type = "IMS"
    ims_log.insert()
