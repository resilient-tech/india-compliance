# Copyright (c) 2022, Resilient Tech and contributors
# For license information, please see license.txt

import json
from typing import List

import frappe
from frappe.model.document import Document
from frappe.query_builder.functions import IfNull
from frappe.utils.response import json_handler

from india_compliance.gst_india.constants import ORIGINAL_VS_AMENDED
from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    BaseUtil,
    BillOfEntry,
    PurchaseInvoice,
    ReconciledData,
    Reconciler,
)
from india_compliance.gst_india.utils import get_json_from_file, get_timespan_date_range
from india_compliance.gst_india.utils.exporter import ExcelExporter
from india_compliance.gst_india.utils.gstr import (
    IMPORT_CATEGORY,
    GSTRCategory,
    ReturnsAPI,
    ReturnType,
    download_gstr_2a,
    download_gstr_2b,
    save_gstr_2a,
    save_gstr_2b,
)

STATUS_MAP = {
    "Accept My Values": "Reconciled",
    "Accept Supplier Values": "Reconciled",
    "Pending": "Unreconciled",
    "Ignore": "Ignored",
}


class PurchaseReconciliationTool(Document):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ReconciledData = ReconciledData(**self.get_reco_doc())

    def get_reco_doc(self):
        fields = (
            "company",
            "company_gstin",
            "gst_return",
            "purchase_from_date",
            "purchase_to_date",
            "inward_supply_from_date",
            "inward_supply_to_date",
            "include_ignored",
        )
        return {field: self.get(field) for field in fields}

    def onload(self):
        date_range = [
            self.inward_supply_from_date,
            self.inward_supply_to_date,
        ]

        self.set_onload(
            "has_missing_2b_documents",
            has_missing_2b_documents(date_range, ReturnType.GSTR2B, self.company_gstin),
        )

    def validate(self):
        # reconcile purchases and inward supplies
        if frappe.flags.in_install or frappe.flags.in_migrate:
            return

        _Reconciler = Reconciler(**self.get_reco_doc())
        for row in ORIGINAL_VS_AMENDED:
            _Reconciler.reconcile(row["original"], row["amended"])

        self.ReconciledData = ReconciledData(**self.get_reco_doc())
        self.reconciliation_data = json.dumps(
            self.ReconciledData.get(), default=json_handler
        )

        self.db_set("is_modified", 0)

    @frappe.whitelist()
    def upload_gstr(self, return_type, period, file_path):
        frappe.has_permission("Purchase Reconciliation Tool", "write", throw=True)

        return_type = ReturnType(return_type)
        json_data = get_json_from_file(file_path)
        if return_type == ReturnType.GSTR2A:
            return save_gstr_2a(self.company_gstin, period, json_data)

        if return_type == ReturnType.GSTR2B:
            return save_gstr_2b(self.company_gstin, period, json_data)

    @frappe.whitelist()
    def download_gstr_2a(self, date_range, force=False, otp=None):
        frappe.has_permission("Purchase Reconciliation Tool", "write", throw=True)

        return_type = ReturnType.GSTR2A
        periods = BaseUtil.get_periods(date_range, return_type)
        if not force:
            periods = self.get_periods_to_download(return_type, periods)

        return download_gstr_2a(self.company_gstin, periods, otp)

    @frappe.whitelist()
    def download_gstr_2b(self, date_range, otp=None):
        frappe.has_permission("Purchase Reconciliation Tool", "write", throw=True)

        return_type = ReturnType.GSTR2B
        periods = self.get_periods_to_download(
            return_type, BaseUtil.get_periods(date_range, return_type)
        )
        return download_gstr_2b(self.company_gstin, periods, otp)

    def get_periods_to_download(self, return_type, periods):
        existing_periods = get_import_history(
            self.company_gstin,
            return_type,
            periods,
            pluck="return_period",
        )

        return [period for period in periods if period not in existing_periods]

    @frappe.whitelist()
    def get_import_history(self, return_type, date_range, for_download=True):
        frappe.has_permission("Purchase Reconciliation Tool", "write", throw=True)

        if not return_type:
            return

        return_type = ReturnType(return_type)
        periods = BaseUtil.get_periods(date_range, return_type, True)
        history = get_import_history(self.company_gstin, return_type, periods)

        columns = [
            "Period",
            "Classification",
            "Status",
            f"{'Downloaded' if for_download else 'Uploaded'} On",
        ]

        settings = frappe.get_cached_doc("GST Settings")

        data = {}
        for period in periods:
            # TODO: skip if today is not greater than 14th return period's next months
            data[period] = []
            status = "🟢 &nbsp; Downloaded"
            for category in GSTRCategory:
                if category.value == "ISDA" and return_type == ReturnType.GSTR2A:
                    continue

                if (
                    not settings.enable_overseas_transactions
                    and category.value in IMPORT_CATEGORY
                ):
                    continue

                download = next(
                    (
                        log
                        for log in history
                        if log.return_period == period
                        and log.classification in (category.value, "")
                    ),
                    None,
                )

                status = "🟠 &nbsp; Not Downloaded"
                if download:
                    status = "🟢 &nbsp; Downloaded"
                    if download.data_not_found:
                        status = "🔵 &nbsp; Data Not Found"
                    if download.request_id:
                        status = "🔵 &nbsp; Queued"

                if not for_download:
                    status = status.replace("Downloaded", "Uploaded")

                _dict = {
                    "Classification": (
                        category.value if return_type is ReturnType.GSTR2A else "ALL"
                    ),
                    "Status": status,
                    columns[-1]: (
                        "✅ &nbsp;"
                        + download.last_updated_on.strftime("%d-%m-%Y %H:%M:%S")
                        if download
                        else ""
                    ),
                }
                if _dict not in data[period]:
                    data[period].append(_dict)

        return {"columns": columns, "data": data}

    @frappe.whitelist()
    def get_return_period_from_file(self, return_type, file_path):
        """
        Permissions check not necessary as response is not sensitive
        """
        if not file_path:
            return

        return_type = ReturnType(return_type)
        try:
            json_data = get_json_from_file(file_path)
            if return_type == ReturnType.GSTR2A:
                return json_data.get("fp")

            if return_type == ReturnType.GSTR2B:
                return json_data.get("data").get("rtnprd")

        except Exception:
            pass

    @frappe.whitelist()
    def get_date_range(self, period):
        """
        Permissions check not necessary as response is not sensitive
        """
        if not period or period == "Custom":
            return

        return get_timespan_date_range(period.lower(), self.company)

    @frappe.whitelist()
    def get_date_range_and_check_missing_documents(self, period):
        date_range = self.get_date_range(period)

        if not date_range:
            return

        self.set_onload(
            "has_missing_2b_documents",
            has_missing_2b_documents(date_range, ReturnType.GSTR2B, self.company_gstin),
        )

        return date_range

    @frappe.whitelist()
    def get_invoice_details(self, purchase_name, inward_supply_name):
        frappe.has_permission("Purchase Reconciliation Tool", "write", throw=True)

        return self.ReconciledData.get_manually_matched_data(
            purchase_name, inward_supply_name
        )

    @frappe.whitelist()
    def link_documents(self, purchase_invoice_name, inward_supply_name, link_doctype):
        frappe.has_permission("Purchase Reconciliation Tool", "write", throw=True)

        if not purchase_invoice_name or not inward_supply_name:
            return

        purchases = []
        inward_supplies = []

        # silently handle existing links
        if isup_linked_with := frappe.db.get_value(
            "GST Inward Supply", inward_supply_name, "link_name"
        ):
            self._unlink_documents((inward_supply_name,))
            purchases.append(isup_linked_with)

        link_doc = {
            "link_doctype": link_doctype,
            "link_name": purchase_invoice_name,
        }
        if pur_linked_with := frappe.db.get_all(
            "GST Inward Supply", link_doc, pluck="name"
        ):
            self._unlink_documents((pur_linked_with))
            inward_supplies.extend(pur_linked_with)

        link_doc["match_status"] = "Manual Match"

        # link documents
        frappe.db.set_value(
            "GST Inward Supply",
            inward_supply_name,
            link_doc,
        )
        purchases.append(purchase_invoice_name)
        inward_supplies.append(inward_supply_name)

        self.db_set("is_modified", 1)

        return self.ReconciledData.get(purchases, inward_supplies)

    @frappe.whitelist()
    def unlink_documents(self, data):
        frappe.has_permission("Purchase Reconciliation Tool", "write", throw=True)

        data = frappe.parse_json(data)
        inward_supplies = set()
        purchases = set()
        boe = set()

        for doc in data:
            inward_supplies.add(doc.get("inward_supply_name"))

            purchase_doctype = doc.get("purchase_doctype")
            if purchase_doctype == "Purchase Invoice":
                purchases.add(doc.get("purchase_invoice_name"))

            elif purchase_doctype == "Bill of Entry":
                boe.add(doc.get("purchase_invoice_name"))

        self.set_reconciliation_status("Purchase Invoice", purchases, "Unreconciled")
        self.set_reconciliation_status("Bill of Entry", boe, "Unreconciled")
        self._unlink_documents(inward_supplies)

        self.db_set("is_modified", 1)

        return self.ReconciledData.get(purchases.union(boe), inward_supplies)

    def set_reconciliation_status(self, doctype, names, status):
        if not names:
            return

        frappe.db.set_value(
            doctype, {"name": ("in", names)}, "reconciliation_status", status
        )

    def _unlink_documents(self, inward_supplies):
        if not inward_supplies:
            return

        GSTR2 = frappe.qb.DocType("GST Inward Supply")
        (
            frappe.qb.update(GSTR2)
            .set("link_doctype", "")
            .set("link_name", "")
            .set("match_status", "Unlinked")
            .where(GSTR2.name.isin(inward_supplies))
            .run()
        )

        # Revert action performed
        (
            frappe.qb.update(GSTR2)
            .set("action", "No Action")
            .where(GSTR2.name.isin(inward_supplies))
            .where(GSTR2.action.notin(("Ignore", "Pending")))
            .run()
        )

    @frappe.whitelist()
    def apply_action(self, data, action):
        frappe.has_permission("Purchase Reconciliation Tool", "write", throw=True)

        data = frappe.parse_json(data)
        status = STATUS_MAP.get(action)

        inward_supplies = []
        purchases = []
        boe = []

        for doc in data:
            if action == "Ignore" and "Missing" not in doc.get("match_status"):
                continue

            elif "Accept" in action and "Missing" in doc.get("match_status"):
                continue

            if inward_supply_name := doc.get("inward_supply_name"):
                inward_supplies.append(inward_supply_name)

            purchase_doctype = doc.get("purchase_doctype")
            if purchase_doctype == "Purchase Invoice":
                purchases.append(doc.get("purchase_invoice_name"))

            elif purchase_doctype == "Bill of Entry":
                boe.append(doc.get("purchase_invoice_name"))

        if inward_supplies:
            frappe.db.set_value(
                "GST Inward Supply", {"name": ("in", inward_supplies)}, "action", action
            )

        self.set_reconciliation_status("Purchase Invoice", purchases, status)
        self.set_reconciliation_status("Bill of Entry", boe, status)

        self.db_set("is_modified", 1)

    @frappe.whitelist()
    def get_link_options(self, doctype, filters):
        frappe.has_permission("Purchase Reconciliation Tool", "write", throw=True)

        if isinstance(filters, dict):
            filters = frappe._dict(filters)

        if doctype == "Purchase Invoice":
            return self.get_purchase_invoice_options(filters)

        elif doctype == "GST Inward Supply":
            return self.get_inward_supply_options(filters)

        elif doctype == "Bill of Entry":
            return self.get_bill_of_entry_options(filters)

    def get_purchase_invoice_options(self, filters):
        PI = frappe.qb.DocType("Purchase Invoice")
        query = (
            self.ReconciledData.query_purchase_invoice(["gst_category", "is_return"])
            .where(PI.supplier_gstin.like(f"%{filters.supplier_gstin}%"))
            .where(PI.bill_date[filters.bill_from_date : filters.bill_to_date])
        )

        if not filters.show_matched:
            query = query.where(
                PI.name.notin(PurchaseInvoice.query_matched_purchase_invoice())
            )

        return self._get_link_options(query.run(as_dict=True))

    def get_inward_supply_options(self, filters):
        GSTR2 = frappe.qb.DocType("GST Inward Supply")
        query = (
            self.ReconciledData.query_inward_supply(["classification"])
            .where(IfNull(GSTR2.supplier_gstin, "").like(f"%{filters.supplier_gstin}%"))
            .where(GSTR2.bill_date[filters.bill_from_date : filters.bill_to_date])
        )

        if filters.get("purchase_doctype") == "Purchase Invoice":
            query = query.where(GSTR2.classification.notin(IMPORT_CATEGORY))
        elif filters.get("purchase_doctype") == "Bill of Entry":
            query = query.where(GSTR2.classification.isin(IMPORT_CATEGORY))

        if not filters.show_matched:
            query = query.where(IfNull(GSTR2.link_name, "") == "")

        return self._get_link_options(query.run(as_dict=True))

    def get_bill_of_entry_options(self, filters):
        BOE = frappe.qb.DocType("Bill of Entry")
        query = self.ReconciledData.query_bill_of_entry().where(
            BOE.bill_of_entry_date[filters.bill_from_date : filters.bill_to_date]
        )

        if not filters.show_matched:
            query = query.where(
                BOE.name.notin(BillOfEntry.query_matched_bill_of_entry())
            )

        return self._get_link_options(query.run(as_dict=True))

    def _get_link_options(self, data):
        for row in data:
            row.value = row.label = row.name
            if not row.get("classification"):
                row.classification = self.ReconciledData.guess_classification(row)

            row.description = (
                f"{row.bill_no}, {row.bill_date}, Taxable Amount: {row.taxable_value}"
            )
            row.description += (
                f", Tax Amount: {BaseUtil.get_total_tax(row)}, {row.classification}"
            )

        return data


def get_import_history(
    company_gstin, return_type: ReturnType, periods: List[str], fields=None, pluck=None
):
    if not (fields or pluck):
        fields = (
            "return_period",
            "classification",
            "data_not_found",
            "last_updated_on",
            "request_id",
        )

    return frappe.db.get_all(
        "GSTR Import Log",
        filters={
            "gstin": company_gstin,
            "return_type": return_type.value,
            "return_period": ("in", periods),
        },
        fields=fields,
        pluck=pluck,
    )


def has_missing_2b_documents(date_range, return_type: ReturnType, company_gstin):
    periods = BaseUtil.get_periods(date_range, return_type, True)

    if not periods:
        return False

    history = get_import_history(company_gstin, return_type, periods)

    if not history:
        return True

    for period in periods:
        download = next((log for log in history if log.return_period == period), None)
        if not download or download.data_not_found or download.request_id:
            return True

    return False


@frappe.whitelist()
def generate_excel_attachment(data, doc):
    frappe.has_permission("Purchase Reconciliation Tool", "email", throw=True)

    build_data = BuildExcel(doc, data, is_supplier_specific=True, email=True)

    xlsx_file, filename = build_data.export_data()
    xlsx_data = xlsx_file.getvalue()

    # Upload attachment for email xlsx data using communication make() method
    folder = frappe.form_dict.folder or "Home"
    file_url = frappe.form_dict.file_url or ""

    file = frappe.get_doc(
        {
            "doctype": "File",
            "attached_to_doctype": "Purchase Reconciliation Tool",
            "attached_to_name": "Purchase Reconciliation Tool",
            "folder": folder,
            "file_name": f"{filename}.xlsx",
            "file_url": file_url,
            "is_private": 0,
            "content": xlsx_data,
        }
    )
    file.save(ignore_permissions=True)
    return [file]


@frappe.whitelist()
def download_excel_report(data, doc, is_supplier_specific=False):
    frappe.has_permission("Purchase Reconciliation Tool", "export", throw=True)

    build_data = BuildExcel(doc, data, is_supplier_specific)
    build_data.export_data()


def parse_params(fun):
    def wrapper(*args, **kwargs):
        args = (frappe.parse_json(arg) for arg in args)
        kwargs = {k: frappe.parse_json(v) for k, v in kwargs.items()}
        return fun(*args, **kwargs)

    return wrapper


@frappe.whitelist()
def resend_otp(company_gstin):
    frappe.has_permission("Purchase Reconciliation Tool", "write", throw=True)

    return ReturnsAPI(company_gstin).request_otp()


class BuildExcel:
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

    @parse_params
    def __init__(self, doc, data, is_supplier_specific=False, email=False):
        """
        :param doc: purchase reconciliation tool doc
        :param data: data to be exported
        :param is_supplier_specific: if true, data will be downloded for specific supplier
        :param email: send the file as email
        """
        self.doc = doc
        self.data = data
        self.is_supplier_specific = is_supplier_specific
        self.email = email
        self.set_headers()
        self.set_filters()

    def export_data(self):
        """Exports data to an excel file"""
        excel = ExcelExporter()
        excel.create_sheet(
            sheet_name="Match Summary Data",
            filters=self.filters,
            headers=self.match_summary_header,
            data=self.get_match_summary_data(),
        )

        if not self.is_supplier_specific:
            excel.create_sheet(
                sheet_name="Supplier Data",
                filters=self.filters,
                headers=self.supplier_header,
                data=self.get_supplier_data(),
            )

        excel.create_sheet(
            sheet_name="Invoice Data",
            filters=self.filters,
            merged_headers=self.get_merge_headers(),
            headers=self.invoice_header,
            data=self.get_invoice_data(),
        )

        excel.remove_sheet("Sheet")

        file_name = self.get_file_name()
        if self.email:
            xlsx_data = excel.save_workbook()
            return [xlsx_data, file_name]

        excel.export(file_name)

    def set_headers(self):
        """Sets headers for the excel file"""

        self.match_summary_header = self.get_match_summary_columns()
        self.supplier_header = self.get_supplier_columns()
        self.invoice_header = self.get_invoice_columns()

    def set_filters(self):
        """Add filters to the sheet"""

        label = "2B" if self.doc.gst_return == "GSTR 2B" else "2A/2B"
        self.period = (
            f"{self.doc.inward_supply_from_date} to {self.doc.inward_supply_to_date}"
        )

        self.filters = frappe._dict(
            {
                "Company Name": self.doc.company,
                "GSTIN": self.doc.company_gstin,
                f"Return Period ({label})": self.period,
            }
        )

    def get_merge_headers(self):
        """Returns merged_headers for the excel file"""
        return frappe._dict(
            {
                "2A / 2B": ["inward_supply_bill_no", "inward_supply_cess"],
                "Purchase Data": ["bill_no", "cess"],
            }
        )

    def get_match_summary_data(self):
        return self.process_data(
            self.data.get("match_summary"),
            self.match_summary_header,
        )

    def get_supplier_data(self):
        return self.process_data(
            self.data.get("supplier_summary"), self.supplier_header
        )

    def get_invoice_data(self):
        data = ReconciledData(**self.doc).get_consolidated_data(
            self.data.get("purchases"),
            self.data.get("inward_supplies"),
            prefix="inward_supply",
        )

        # TODO: Sanitize supplier name and gstin
        self.supplier_name = data[0].get("supplier_name")
        self.supplier_gstin = data[0].get("supplier_gstin")

        return self.process_data(data, self.invoice_header)

    def process_data(self, data, column_list):
        """return required list of dict for the excel file"""
        if not data:
            return

        out = []
        fields = [d.get("fieldname") for d in column_list]
        purchase_fields = [field.get("fieldname") for field in self.pr_columns]
        for row in data:
            new_row = {}
            for field in fields:
                if field not in row:
                    row[field] = None

                # pur data in row (for invoice_summary) is polluted for Missing in PI
                if field in purchase_fields and not row.get("name"):
                    row[field] = None

                self.assign_value(field, row, new_row)

            out.append(new_row)

        return out

    def assign_value(self, field, source_data, target_data):
        if source_data.get(field) is None:
            target_data[field] = None
            return

        if "is_reverse_charge" in field:
            target_data[field] = "Yes" if source_data.get(field) else "No"
            return

        target_data[field] = source_data.get(field)

    def get_file_name(self):
        """Returns file name for the excel file"""
        if not self.is_supplier_specific:
            return f"{self.doc.company_gstin}_{self.period}_report"

        file_name = f"{self.supplier_name}_{self.supplier_gstin}"
        return file_name.replace(" ", "_")

    def get_match_summary_columns(self):
        """
        Defaults:
            - bg_color: self.COLOR_PALLATE.dark_gray
            - bg_color_data": self.COLOR_PALLATE.light_gray
            - bold: 1
            - align_header: "center"
            - align_data: "general"
            - width: 20
        """
        return [
            {
                "label": "Match Status",
                "fieldname": "match_status",
                "data_format": {"horizontal": "left"},
                "header_format": {"horizontal": "center"},
            },
            {
                "label": "Count \n 2A/2B Docs",
                "fieldname": "inward_supply_count",
                "fieldtype": "Int",
                "data_format": {"number_format": "#,##0"},
            },
            {
                "label": "Count \n Purchase Docs",
                "fieldname": "purchase_count",
                "fieldtype": "Int",
                "data_format": {"number_format": "#,##0"},
            },
            {
                "label": "Taxable Amount Diff \n 2A/2B - Purchase",
                "fieldname": "taxable_value_difference",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                },
            },
            {
                "label": "Tax Difference \n 2A/2B - Purchase",
                "fieldname": "tax_difference",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                },
            },
            {
                "label": "%Action Taken",
                "fieldname": "action_taken_count",
                "data_format": {"number_format": "0.00%"},
                "width": 12,
            },
        ]

    def get_supplier_columns(self):
        return [
            {
                "label": "Supplier Name",
                "fieldname": "supplier_name",
                "data_format": {"horizontal": "left"},
            },
            {
                "label": "Supplier GSTIN",
                "fieldname": "supplier_gstin",
                "data_format": {"horizontal": "left"},
            },
            {
                "label": "Count \n 2A/2B Docs",
                "fieldname": "inward_supply_count",
                "fieldtype": "Int",
                "data_format": {"number_format": "#,##0"},
            },
            {
                "label": "Count \n Purchase Docs",
                "fieldname": "purchase_count",
                "fieldtype": "Int",
                "data_format": {
                    "number_format": "#,##0",
                },
            },
            {
                "label": "Taxable Amount Diff \n 2A/2B - Purchase",
                "fieldname": "taxable_value_difference",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                },
            },
            {
                "label": "Tax Difference \n 2A/2B - Purchase",
                "fieldname": "tax_difference",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                },
            },
            {
                "label": "%Action Taken",
                "fieldname": "action_taken_count",
                "data_format": {"number_format": "0.00%"},
                "header_format": {
                    "width": 12,
                },
            },
        ]

    def get_invoice_columns(self):
        self.pr_columns = [
            {
                "label": "Bill No",
                "fieldname": "bill_no",
                "compare_with": "inward_supply_bill_no",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
            {
                "label": "Bill Date",
                "fieldname": "bill_date",
                "compare_with": "inward_supply_bill_date",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
            {
                "label": "GSTIN",
                "fieldname": "supplier_gstin",
                "compare_with": "inward_supply_supplier_gstin",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 15,
                },
            },
            {
                "label": "Place of Supply",
                "fieldname": "place_of_supply",
                "compare_with": "inward_supply_place_of_supply",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
            {
                "label": "Reverse Charge",
                "fieldname": "is_reverse_charge",
                "compare_with": "inward_supply_is_reverse_charge",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
            {
                "label": "Taxable Value",
                "fieldname": "taxable_value",
                "compare_with": "inward_supply_taxable_value",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
            {
                "label": "CGST",
                "fieldname": "cgst",
                "compare_with": "inward_supply_cgst",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
            {
                "label": "SGST",
                "fieldname": "sgst",
                "compare_with": "inward_supply_sgst",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
            {
                "label": "IGST",
                "fieldname": "igst",
                "compare_with": "inward_supply_igst",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
            {
                "label": "CESS",
                "fieldname": "cess",
                "compare_with": "inward_supply_cess",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
        ]
        self.inward_supply_columns = [
            {
                "label": "Bill No",
                "fieldname": "inward_supply_bill_no",
                "compare_with": "bill_no",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
            {
                "label": "Bill Date",
                "fieldname": "inward_supply_bill_date",
                "compare_with": "bill_date",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
            {
                "label": "GSTIN",
                "fieldname": "inward_supply_supplier_gstin",
                "compare_with": "supplier_gstin",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 15,
                },
            },
            {
                "label": "Place of Supply",
                "fieldname": "inward_supply_place_of_supply",
                "compare_with": "place_of_supply",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
            {
                "label": "Reverse Charge",
                "fieldname": "inward_supply_is_reverse_charge",
                "compare_with": "is_reverse_charge",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
            {
                "label": "Taxable Value",
                "fieldname": "inward_supply_taxable_value",
                "compare_with": "taxable_value",
                "fieldtype": "Float",
                "data_format": {
                    "number_format": "0.00",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
            {
                "label": "CGST",
                "fieldname": "inward_supply_cgst",
                "compare_with": "cgst",
                "fieldtype": "Float",
                "data_format": {
                    "number_format": "0.00",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
            {
                "label": "SGST",
                "fieldname": "inward_supply_sgst",
                "compare_with": "sgst",
                "fieldtype": "Float",
                "data_format": {
                    "number_format": "0.00",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
            {
                "label": "IGST",
                "fieldname": "inward_supply_igst",
                "compare_with": "igst",
                "fieldtype": "Float",
                "data_format": {
                    "number_format": "0.00",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
            {
                "label": "CESS",
                "fieldname": "inward_supply_cess",
                "compare_with": "cess",
                "fieldtype": "Float",
                "data_format": {
                    "number_format": "0.00",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
        ]
        inv_columns = [
            {
                "label": "Action Status",
                "fieldname": "action",
                "data_format": {"horizontal": "left"},
            },
            {
                "label": "Match Status",
                "fieldname": "match_status",
                "data_format": {"horizontal": "left"},
            },
            {
                "label": "Supplier Name",
                "fieldname": "supplier_name",
                "data_format": {"horizontal": "left"},
            },
            {
                "label": "PAN",
                "fieldname": "pan",
                "data_format": {"horizontal": "center"},
                "header_format": {
                    "width": 15,
                },
            },
            {
                "label": "Classification",
                "fieldname": "classification",
                "data_format": {"horizontal": "left"},
                "header_format": {
                    "width": 11,
                },
            },
            {
                "label": "Taxable Value Difference",
                "fieldname": "taxable_value_difference",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": 12,
                },
            },
            {
                "label": "Tax Difference",
                "fieldname": "tax_difference",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": 12,
                },
            },
        ]
        inv_columns.extend(self.inward_supply_columns)
        inv_columns.extend(self.pr_columns)
        return inv_columns
