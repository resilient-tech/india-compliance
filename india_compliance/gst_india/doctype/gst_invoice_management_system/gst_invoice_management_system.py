# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import IfNull
from frappe.utils import add_to_date, format_date

from india_compliance.gst_india.api_classes.taxpayer_base import (
    TaxpayerBaseAPI,
    otp_handler,
)
from india_compliance.gst_india.api_classes.taxpayer_returns import IMSAPI
from india_compliance.gst_india.constants import STATUS_CODE_MAP
from india_compliance.gst_india.doctype.gst_invoice_management_system import (
    IMSReconciler,
    InwardSupply,
    PurchaseInvoice,
)
from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    verify_request_in_progress,
)
from india_compliance.gst_india.doctype.gstr_action.gstr_action import set_gstr_actions
from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    ReconciledData,
)
from india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_tool import (
    BuildExcel,
)
from india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_utils import (
    get_formatted_options,
)
from india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_utils import (
    link_documents as _link_documents,
)
from india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_utils import (
    unlink_documents as _unlink_documents,
)
from india_compliance.gst_india.utils.exporter import ExcelExporter
from india_compliance.gst_india.utils.gstin_info import (
    get_latest_3b_filed_period,
    update_gstr_returns_info,
)
from india_compliance.gst_india.utils.gstr_2 import (
    GSTRCategory,
    ReturnType,
    download_ims_invoices,
    get_data_handler,
)
from india_compliance.gst_india.utils.gstr_utils import (
    publish_action_status_notification,
)
from india_compliance.setup_wizard import can_fetch_gstin_info

CATEGORY_MAP = {
    "Invoice_0": GSTRCategory.B2B.value,
    "Invoice_1": GSTRCategory.B2BA.value,
    "Debit Note_0": GSTRCategory.B2BDN.value,
    "Debit Note_1": GSTRCategory.B2BDNA.value,
    "Credit Note_0": GSTRCategory.B2BCN.value,
    "Credit Note_1": GSTRCategory.B2BCNA.value,
}


class GSTInvoiceManagementSystem(Document):
    @frappe.whitelist()
    def autoreconcile_and_get_data(self):
        frappe.has_permission("GST Invoice Management System", "write", throw=True)

        filters = frappe._dict(
            {
                "company": self.company,
                "company_gstin": self.company_gstin,
            }
        )

        # Auto-Reconcile invoices
        IMSReconciler().reconcile(filters)

        return {
            "invoice_data": self.get_invoice_data(filters=filters),
            "pending_actions": self.get_pending_actions(),
        }

    def get_invoice_data(self, inward_supply=None, purchase=None, filters=None):
        if not filters:
            filters = frappe._dict(
                {
                    "company": self.company,
                    "company_gstin": self.company_gstin,
                }
            )

        inward_supplies = InwardSupply().get_all(
            company_gstin=self.company_gstin, names=inward_supply
        )

        if not purchase:
            purchase = [doc.link_name for doc in inward_supplies]

        purchases = PurchaseInvoice().get_all(names=purchase, filters=filters)

        invoice_data = []
        for doc in inward_supplies:
            _purchase_invoice = purchases.pop(doc.link_name, frappe._dict())

            invoice_data.append(
                frappe._dict(
                    {
                        "ims_action": doc.ims_action,
                        "pending_upload": doc.pending_upload,
                        "previous_ims_action": doc.previous_ims_action,
                        "is_pending_action_allowed": doc.is_pending_action_allowed,
                        "is_supplier_return_filed": doc.is_supplier_return_filed,
                        "doc_type": doc.doc_type,
                        "posting_date": format_date(
                            _purchase_invoice.get("posting_date")
                        ),
                        "_inward_supply": doc,
                        "_purchase_invoice": _purchase_invoice,
                    }
                )
            )

        # Missing in 2A/2B is ignored for IMS

        ReconciledData().process_data(invoice_data, retain_doc=True)

        return invoice_data

    def get_pending_actions(self):
        return frappe.get_all(
            "GSTR Action",
            {
                "parent": f"IMS-ALL-{self.company_gstin}",
                "parenttype": "GST Return Log",
                "status": ["is", "not set"],
                "token": ["is", "set"],
            },
            pluck="request_type",
        )

    @frappe.whitelist()
    def update_action(self, invoice_names, action):
        frappe.has_permission("GST Invoice Management System", "write", throw=True)

        invoice_names = frappe.parse_json(invoice_names)
        GSTR2 = frappe.qb.DocType("GST Inward Supply")

        # When invoice is rejected then mark action as "Ignore" and copy current action to previous action
        # only if invoice is not matched
        if action == "Rejected":
            (
                frappe.qb.update(GSTR2)
                .set("previous_action", GSTR2.action)
                .set("action", "Ignore")
                .where(IfNull(GSTR2.link_name, "") == "")
                .where(GSTR2.name.isin(invoice_names))
                .run()
            )

        # When invoice is marked from "Rejected" to any other ims_action then copy previous action to action
        # only if invoice is not matched
        else:
            (
                frappe.qb.update(GSTR2)
                .set("action", GSTR2.previous_action)
                .where(GSTR2.ims_action == "Rejected")
                .where(IfNull(GSTR2.link_name, "") == "")
                .where(GSTR2.name.isin(invoice_names))
                .run()
            )

        # Update ims_action
        (
            frappe.qb.update(GSTR2)
            .set("ims_action", action)
            .where(GSTR2.name.isin(invoice_names))
            .run()
        )

    @frappe.whitelist()
    def get_invoice_details(self, purchase_name, inward_supply_name):
        frappe.has_permission("GST Invoice Management System", "write", throw=True)

        inward_supply = InwardSupply().get_all(
            self.company_gstin, names=[inward_supply_name]
        )
        purchases = PurchaseInvoice().get_all(names=[purchase_name])

        reconciliation_data = [
            frappe._dict(
                {
                    "_inward_supply": (
                        inward_supply[0] if inward_supply else frappe._dict()
                    ),
                    "_purchase_invoice": purchases.get(purchase_name, frappe._dict()),
                }
            )
        ]

        ReconciledData().process_data(reconciliation_data, retain_doc=True)

        return reconciliation_data[0]

    @frappe.whitelist()
    def link_documents(self, purchase_invoice_name, inward_supply_name, link_doctype):
        frappe.has_permission("GST Invoice Management System", "write", throw=True)

        purchases, inward_supplies = _link_documents(
            purchase_invoice_name, inward_supply_name, link_doctype
        )

        return self.get_invoice_data(inward_supplies, purchases)

    @frappe.whitelist()
    def unlink_documents(self, data):
        frappe.has_permission("GST Invoice Management System", "write", throw=True)

        purchases, inward_supplies = _unlink_documents(data)

        return self.get_invoice_data(inward_supplies, purchases)

    @frappe.whitelist()
    def get_link_options(self, doctype, filters):
        frappe.has_permission("GST Invoice Management System", "write", throw=True)

        if isinstance(filters, dict):
            filters = frappe._dict(filters)

        PI = frappe.qb.DocType("Purchase Invoice")
        query = (
            PurchaseInvoice()
            .get_query(additional_fields=["gst_category", "is_return"])
            .where(PI.supplier_gstin.like(f"%{filters.supplier_gstin}%"))
            .where(PI.bill_date[filters.bill_from_date : filters.bill_to_date])
        )

        if not filters.show_matched:
            query = query.where(PI.reconciliation_status == "Unreconciled")

        return get_formatted_options(query.run(as_dict=True))


@frappe.whitelist()
@otp_handler
def download_invoices(company_gstin):
    frappe.has_permission("GST Invoice Management System", "write", throw=True)

    TaxpayerBaseAPI(company_gstin).validate_auth_token()

    frappe.enqueue(download_ims_invoices, queue="long", gstin=company_gstin)


@frappe.whitelist()
@otp_handler
def save_invoices(company_gstin):
    frappe.has_permission("GST Invoice Management System", "write", throw=True)
    frappe.has_permission("GST Return Log", "write", throw=True)

    return save_ims_invoices(company_gstin)


@frappe.whitelist()
@otp_handler
def reset_invoices(company_gstin):
    frappe.has_permission("GST Invoice Management System", "write", throw=True)
    frappe.has_permission("GST Return Log", "write", throw=True)

    return reset_ims_invoices(company_gstin)


@frappe.whitelist()
@otp_handler
def sync_with_gstn_and_reupload(company_gstin):
    frappe.has_permission("GST Invoice Management System", "write", throw=True)
    frappe.has_permission("GST Return Log", "write", throw=True)

    TaxpayerBaseAPI(company_gstin).validate_auth_token()

    frappe.enqueue(
        download_and_upload_ims_invoices,
        queue="long",
        company_gstin=company_gstin,
    )


@frappe.whitelist()
@otp_handler
def check_action_status(company_gstin, action):
    frappe.has_permission("GST Return Log", "write", throw=True)

    ims_log = frappe.get_doc(
        "GST Return Log",
        f"IMS-ALL-{company_gstin}",
    )

    return process_save_or_reset_ims(ims_log, action)


@frappe.whitelist()
def download_excel_report(data, doc):
    frappe.has_permission("GST Invoice Management System", "export", throw=True)

    build_data = BuildExcelIMS(doc, data)
    build_data.export_data()


@frappe.whitelist()
def get_period_options(company, company_gstin):
    def format_period(period):
        return period[2:] + period[:2]

    # Calculate six months ago as fallback
    six_months_ago = add_to_date(None, months=-7).strftime("%m%Y")
    latest_3b_filed_period = get_latest_3b_filed_period(company, company_gstin) or (
        six_months_ago,
    )

    # Fetch latest GSTR3B filing or default to six months ago
    latest_3b_filed_period = format_period(latest_3b_filed_period[0])
    six_months_ago = format_period(six_months_ago)

    if latest_3b_filed_period <= six_months_ago and can_fetch_gstin_info():
        update_gstr_returns_info(company, company_gstin)

    # Generate last six months of valid periods
    periods = []
    date = add_to_date(None, months=-1)

    while True:
        period = date.strftime("%m%Y")
        formatted_period = format_period(period)

        if formatted_period <= latest_3b_filed_period or formatted_period < "201707":
            break

        periods.append(period)
        date = add_to_date(date, months=-1)

    return periods


def download_and_upload_ims_invoices(company_gstin):
    """
    1. This function will download invoices from GST Portal,
       and if there are some queued invoices then upload will be skipped.

    2. If there are no queued invoices, then it will upload the invoices to GST Portal.

    3. It will check the status regardless of whether any data was uploaded or not.
       (To notify user that process is completed successfully).
    """

    has_queued_invoices = download_ims_invoices(company_gstin, for_upload=True)

    # TODO: flag for pending upload and cron job for queued invoices
    if has_queued_invoices:
        return

    frappe.publish_realtime(
        "upload_data_and_check_status",
        user=frappe.session.user,
    )


def save_ims_invoices(company_gstin):
    if not frappe.db.exists("GST Return Log", f"IMS-ALL-{company_gstin}"):
        frappe.throw(_("Please download invoices before uploading"))

    ims_log = frappe.get_doc(
        "GST Return Log",
        f"IMS-ALL-{company_gstin}",
    )

    save_data = get_data_for_upload(company_gstin, "save")

    if not save_data:
        return

    verify_request_in_progress(ims_log, False)

    api = IMSAPI(company_gstin)

    # Upload invoices where action in ["Accepted", "Rejected", "Pending"]
    response = api.save(save_data)
    set_gstr_actions(ims_log, "save", response.get("reference_id"), api.request_id)


def reset_ims_invoices(company_gstin):
    if not frappe.db.exists("GST Return Log", f"IMS-ALL-{company_gstin}"):
        frappe.throw(_("Please download invoices before uploading"))

    ims_log = frappe.get_doc(
        "GST Return Log",
        f"IMS-ALL-{company_gstin}",
    )

    reset_data = get_data_for_upload(company_gstin, "reset")

    if not reset_data:
        return

    verify_request_in_progress(ims_log, False)

    api = IMSAPI(company_gstin)

    # Reset invoices where action is "No Action"
    response = api.reset(reset_data)
    set_gstr_actions(ims_log, "reset", response.get("reference_id"), api.request_id)


def get_data_for_upload(company_gstin, request_type):
    upload_data = {}
    key_invoice_map = {}

    if request_type == "save":
        gst_inward_supply_list = InwardSupply().get_for_save(company_gstin)
    else:
        gst_inward_supply_list = InwardSupply().get_for_reset(company_gstin)

    for invoice in gst_inward_supply_list:
        key = f"{invoice.doc_type}_{invoice.is_amended}"
        key_invoice_map.setdefault(key, []).append(invoice)

    for key, invoices in key_invoice_map.items():
        category = CATEGORY_MAP[key]
        _class = get_data_handler(ReturnType.IMS.value, category)()
        upload_invoices = []

        for invoice in invoices:
            upload_invoices.append(
                {
                    **_class.convert_data_to_gov_format(invoice),
                    **_class.get_category_details(invoice),
                }
            )

        if upload_invoices:
            upload_data[category.lower()] = upload_invoices

    return upload_data


def process_save_or_reset_ims(return_log, action):
    response = {"status_cd": "P"}  # dummy_response
    doc = return_log.get_unprocessed_action(action)
    if not doc:
        return response

    api = IMSAPI(return_log.gstin)
    response = api.get_request_status(doc.token)

    status_cd = response.get("status_cd")

    if status_cd != "IP":
        doc.db_set({"status": STATUS_CODE_MAP.get(status_cd)})
        publish_action_status_notification(
            "IMS",
            return_log.return_period,
            doc.request_type,
            status_cd,
            return_log.gstin,
            api.request_id if status_cd == "ER" else None,
        )

    if status_cd in ["P", "PE"]:
        # Exclude erroneous invoices from previous IMS action update
        # This is enqueued because creation of integration request is enqueued
        # TODO: flag for re-upload?
        frappe.enqueue(
            update_previous_ims_action,
            queue="long",
            request_id=doc.request_id,
            error_report=response.get("error_report") or dict(),
        )

    return response


def update_previous_ims_action(request_id, error_report=None):
    uploaded_invoices = get_uploaded_invoices(request_id)

    for category, invoices in uploaded_invoices.items():
        _class = get_data_handler(ReturnType.IMS.value, category.upper())
        _class().update_previous_ims_action(invoices, error_report.get(category, []))


def get_uploaded_invoices(request_id):
    request_data = frappe.parse_json(
        frappe.db.get_value("Integration Request", {"request_id": request_id}, "data")
    )

    if not request_data:
        frappe.throw(
            _(
                "Integration Request linked with data upload not found for request id {0}"
            ).format(request_id)
        )

    if isinstance(request_data, str):
        request_data = frappe.parse_json(request_data)

    return request_data["body"]["data"]["invdata"]


class BuildExcelIMS(BuildExcel):
    def export_data(self):
        """Exports data to an excel file"""
        excel = ExcelExporter()
        excel.create_sheet(
            sheet_name="Invoice Data",
            filters=self.filters,
            headers=self.invoice_header,
            data=self.data,
            default_data_format={"horizontal": "center"},
            default_header_format={"bg_color": self.COLOR_PALLATE.dark_gray},
        )

        excel.remove_sheet("Sheet")
        file_name = self.get_file_name()
        excel.export(file_name)

    def set_headers(self):
        """Sets headers for the excel file"""
        self.invoice_header = self.get_invoice_columns()

    def set_filters(self):
        """Add filters to the sheet"""
        self.filters = frappe._dict(
            {
                "Company Name": self.doc.company,
                "GSTIN": self.doc.company_gstin,
            }
        )

    def get_file_name(self):
        """Returns file name for the excel file"""
        return f"{self.doc.company}_{self.doc.company_gstin}_report"

    def get_invoice_columns(self):
        return [
            {
                "label": "Supplier Name",
                "fieldname": "supplier_name",
                "header_format": {"width": 35},
            },
            {
                "label": "Supplier GSTIN",
                "fieldname": "supplier_gstin",
            },
            {
                "label": "Bill No",
                "fieldname": "bill_no",
            },
            {
                "label": "Bill Date",
                "fieldname": "bill_date",
            },
            {
                "label": "Match Status",
                "fieldname": "match_status",
            },
            {
                "label": "IMS Action",
                "fieldname": "ims_action",
            },
            {
                "label": "Inward Supply Name",
                "fieldname": "inward_supply_name",
            },
            {
                "label": "Linked Voucher",
                "fieldname": "purchase_invoice_name",
            },
            {
                "label": "Posting Date",
                "fieldname": "posting_date",
            },
            {
                "label": "Taxable Amount Diff \n 2A/2B - Purchase",
                "fieldname": "taxable_value_difference",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": "0.00",
                    "horizontal": "right",
                },
            },
            {
                "label": "Tax Difference \n 2A/2B - Purchase",
                "fieldname": "tax_difference",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": "0.00",
                    "horizontal": "right",
                },
            },
            {
                "label": "Classification",
                "fieldname": "classification",
                "header_format": {"width": 11},
            },
        ]
