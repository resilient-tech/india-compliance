# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.query_builder.functions import IfNull

from india_compliance.gst_india.api_classes.taxpayer_base import otp_handler
from india_compliance.gst_india.api_classes.taxpayer_returns import IMSAPI
from india_compliance.gst_india.doctype.gst_invoice_management_system import (
    IMSReconciler,
)
from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    update_previous_ims_action as _update_previous_ims_action,
)
from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    enqueue_link_integration_request,
    enqueue_notification,
    status_code_map,
    verify_request_in_progress,
)
from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    ReconciledData,
)
from india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_utils import (
    link_documents,
    unlink_documents,
)
from india_compliance.gst_india.utils.gstr_2 import download_ims_invoices, ims


class GSTInvoiceManagementSystem(Document):
    @frappe.whitelist()
    def get_invoice_data(self, inward_supply=None, purchase=None):
        frappe.has_permission("GST Invoice Management System", "write", throw=True)

        filters = {
            "company": self.company,
            "company_gstin": self.company_gstin,
        }

        inward_supplies = self.get_all_inward_supplies(
            names=inward_supply, filters=filters
        )
        purchases = self.get_all_purchases(names=purchase, filters=filters)

        invoice_data = []
        for doc in inward_supplies:
            invoice_data.append(
                frappe._dict(
                    {
                        "ims_action": doc.ims_action,
                        "pending_upload": doc.pending_upload,
                        "previous_ims_action": doc.previous_ims_action,
                        "is_pending_action_allowed": doc.is_pending_action_allowed,
                        "doc_type": doc.doc_type,
                        "_inward_supply": doc,
                        "_purchase_invoice": purchases.pop(
                            doc.link_name, frappe._dict()
                        ),
                    }
                )
            )

        ReconciledData().process_data(invoice_data, retain_doc=True)

        return invoice_data

    @frappe.whitelist()
    def update_action(self, invoice_names, action):
        frappe.has_permission("GST Invoice Management System", "write", throw=True)

        invoice_names = frappe.parse_json(invoice_names)

        frappe.db.set_value(
            "GST Inward Supply",
            {"name": ("in", invoice_names)},
            "ims_action",
            action,
        )

    @frappe.whitelist()
    def get_invoice_comparision(self, purchase_name, inward_supply_name):
        frappe.has_permission("GST Invoice Management System", "write", throw=True)

        self._reconciler_class = IMSReconciler()
        inward_supply = self.get_all_inward_supplies(names=[inward_supply_name])
        purchases = self.get_all_purchases(names=[purchase_name])

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

        purchases, inward_supplies = link_documents(
            purchase_invoice_name, inward_supply_name, link_doctype
        )

        return self.get_invoice_data(inward_supplies, purchases)

    @frappe.whitelist()
    def unlink_documents(self, data):
        frappe.has_permission("GST Invoice Management System", "write", throw=True)

        purchases, inward_supplies = unlink_documents(data)

        return self.get_invoice_data(inward_supplies, purchases)

    def get_all_inward_supplies(self, names=None, filters=None):
        IMS_RECONCILER = IMSReconciler()

        if not filters:
            filters = {}

        query = IMS_RECONCILER.get_base_inward_supply_query(["action", "doc_type"])

        if names:
            query = query.where(IMS_RECONCILER.inward_supply.name.isin(names))

        query = IMS_RECONCILER.get_query_with_filters(
            IMS_RECONCILER.inward_supply, query, filters
        )

        return query.run(as_dict=True)

    def get_all_purchases(self, names=None, filters=None):
        if not filters:
            filters = {}

        purchases = self.get_all_purchase_invoice(names, filters)

        return {doc.name: doc for doc in purchases}

    def get_all_purchase_invoice(self, names, filters):
        IMS_RECONCILER = IMSReconciler()
        query = IMS_RECONCILER.get_base_purchase_query()

        if names:
            query = query.where(IMS_RECONCILER.purchase_invoice.name.isin(names))

        query = IMS_RECONCILER.get_query_with_filters(
            IMS_RECONCILER.purchase_invoice, query, filters
        )

        return query.run(as_dict=True)


@frappe.whitelist()
@otp_handler
def download_invoices_and_reconcile(company_gstin, company):
    frappe.has_permission("GST Invoice Management System", "write", throw=True)

    # Download Invoices
    download_ims_invoices(company_gstin, company)

    # Auto_Reconcile Invoices
    filters = frappe._dict({"company": company, "company_gstin": company_gstin})
    IMSReconciler().auto_reconcile_invoices(filters)


@frappe.whitelist()
@otp_handler
def upload_invoices(company_gstin):
    frappe.has_permission("GST Invoice Management System", "write", throw=True)
    frappe.has_permission("GST Return Log", "write", throw=True)

    ims_log = frappe.get_doc(
        "GST Return Log",
        f"IMS-ALL-{company_gstin}",
    )

    upload_data, reset_data = get_invoices_to_upload(company_gstin)

    if not (upload_data or reset_data):
        return

    verify_request_in_progress(ims_log, False)

    api = IMSAPI(company_gstin)

    if upload_data:
        # Upload invoices where action in ["Accepted", "Rejected", "Pending"]
        response = api.save_ims_action(upload_data)
        update_return_log(
            ims_log, response.get("reference_id"), "upload", api.request_id
        )

    if reset_data:
        # Reset invoices where action is "No Action"
        response = api.reset_ims_action(reset_data)
        update_return_log(
            ims_log, response.get("reference_id"), "reset", api.request_id
        )


@frappe.whitelist()
@otp_handler
def check_action_status(company_gstin):
    frappe.has_permission("GST Return Log", "write", throw=True)

    ims_log = frappe.get_doc(
        "GST Return Log",
        f"IMS-ALL-{company_gstin}",
    )

    return process_upload_ims(ims_log)


def get_invoices_to_upload(company_gstin):
    ims_reconciler = IMSReconciler()
    additional_fields = [
        "doc_type",
        "is_amended",
        "previous_ims_action",
        "ims_action",
        "sup_return_period",
        "document_value",
        "place_of_supply",
        "supply_type",
    ]
    query = ims_reconciler.get_base_inward_supply_query(additional_fields)
    gst_inward_supply_list = (
        query.where(IfNull(ims_reconciler.inward_supply.previous_ims_action, "") != "")
        .where(
            ims_reconciler.inward_supply.ims_action
            != ims_reconciler.inward_supply.previous_ims_action
        )
        .run(as_dict=True)
    )

    upload_data, reset_data = convert_data_to_gov_format(
        gst_inward_supply_list, company_gstin
    )

    return upload_data, reset_data


def convert_data_to_gov_format(gst_inward_supply_list, company_gstin):
    category_key_map = {
        "Invoice_0": "b2b",
        "Invoice_1": "b2ba",
        "Debit Note_0": "b2bdn",
        "Debit Note_1": "b2bdna",
        "Credit Note_0": "b2bcn",
        "Credit Note_1": "b2bcna",
    }

    upload_data = {}
    reset_data = {}
    key_invoice_map = {}

    for invoice in gst_inward_supply_list:
        key = f"{invoice.doc_type}_{invoice.is_amended}"
        if key_invoice_map.get(key):
            key_invoice_map[key].append(invoice)
        else:
            key_invoice_map[key] = [invoice]

    for key, invoices in key_invoice_map.items():
        category = category_key_map[key]
        _class = getattr(ims, category.upper())(company_gstin)
        upload_invoices = []
        reset_invoices = []

        for invoice in invoices:
            data = {
                **_class.update_transaction_to_gov_format(invoice),
                **_class.get_category_details(invoice),
            }

            if invoice.ims_action != "No Action":
                upload_invoices.append(data)
            else:
                reset_invoices.append(data)

        if upload_invoices:
            upload_data[category] = upload_invoices

        if reset_invoices:
            reset_data[category] = reset_invoices

    return upload_data, reset_data


def update_return_log(doc, token, action, request_id, status=None):
    if not token:
        return

    row = {
        "request_type": action,
        "token": token,
        "creation_time": frappe.utils.now_datetime(),
    }

    if status:
        row["status"] = status

    doc.append("actions", row)
    doc.save()
    enqueue_link_integration_request(token, request_id)


def process_upload_ims(return_log):
    if not return_log.actions:
        return

    api = IMSAPI(return_log.gstin)
    response = None

    doc = return_log.get_unprocessed_action("upload")
    if not doc:
        doc = return_log.get_unprocessed_action("reset")

    if not doc:
        return

    response = api.get_request_status(doc.token)
    status_cd = response.get("status_cd")

    erroneous_invoices = []
    if status_cd != "IP":
        doc.db_set({"status": status_code_map.get(status_cd)})
        enqueue_notification(
            return_log.return_period,
            doc.request_type,
            status_cd,
            return_log.gstin,
            api.request_id if status_cd == "ER" else None,
        )

    if status_cd == "PE":
        erroneous_invoices, response["error_report"] = get_erroneous_invoices(
            response.get("error_report")
        )

    if status_cd in ["P", "PE"]:
        # Exclude erroneous invoices from previous IMS action update
        # This is enqueued because linking of integration request is enqueued
        frappe.enqueue(
            "india_compliance.gst_india.doctype.gst_invoice_management_system.gst_invoice_management_system.update_previous_ims_action",
            queue="long",
            return_log=doc,
            erroneous_invoices=erroneous_invoices,
        )

    return response


def get_erroneous_invoices(report):
    error_report = []
    invoice_names = []
    for error_list in report.values():
        for error in error_list:
            for invoice in error.get("inv"):
                error_report.append(
                    {
                        "error_msg": error.get("error_msg"),
                        "error_code": error.get("error_cd"),
                        "invoice": invoice.get("inum"),
                        "return_period": invoice.get("rtnprd"),
                        "supplier_gstin": error.get("stin"),
                    }
                )
                invoice_names.append(f"{invoice.get('inum')}_{error.get('stin')}")

    return invoice_names, error_report


def get_uploaded_invoices(integration_request):
    request_data = frappe.parse_json(
        frappe.db.get_value(
            "Integration Request", {"name": integration_request}, "data"
        )
    )

    return request_data["body"]["data"]["invdata"]


def update_previous_ims_action(return_log, erroneous_invoices):
    integration_request = return_log.integration_request
    uploded_invoices = get_uploaded_invoices(integration_request)

    invoices_to_update = []
    for category, invoices in uploded_invoices.items():
        _class = getattr(ims, category.upper())()
        invoices_to_update.extend(_class.get_all_transactions(invoices))

    for invoice in invoices_to_update:
        if f"{invoice.bill_no}_{invoice.supplier_gstin}" in erroneous_invoices:
            continue

        _update_previous_ims_action(invoice)
