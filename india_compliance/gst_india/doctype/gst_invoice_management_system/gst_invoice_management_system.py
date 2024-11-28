# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.query_builder.functions import IfNull

from india_compliance.gst_india.api_classes.taxpayer_base import otp_handler
from india_compliance.gst_india.api_classes.taxpayer_returns import IMSAPI
from india_compliance.gst_india.constants import STATE_NUMBERS
from india_compliance.gst_india.doctype.gst_invoice_management_system import (
    IMSReconciler,
)
from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    enqueue_link_integration_request,
    status_code_map,
    verify_request_in_progress,
)
from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    ReconciledData,
)
from india_compliance.gst_india.utils.gstr_2 import download_ims_invoices, ims


class GSTInvoiceManagementSystem(Document):
    IMS_RECONCILER = IMSReconciler()

    @frappe.whitelist()
    def get_invoice_data(self):
        frappe.has_permission("GST Invoice Management System", "write", throw=True)

        filters = {
            "company": self.company,
            "company_gstin": self.company_gstin,
        }

        inward_supplies = self.get_all_inward_supplies(filters=filters)
        purchases = self.get_all_purchases(filters=filters)

        invoice_data = []
        for doc in inward_supplies:
            invoice_data.append(
                frappe._dict(
                    {
                        "ims_action": doc.ims_action,
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
        inward_supply = self.get_all_inward_supplies(name=inward_supply_name)
        purchases = self.get_all_purchases(purchase_name)

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

    def get_all_inward_supplies(self, name=None, filters=None):
        if not filters:
            filters = {}

        query = self.IMS_RECONCILER.get_base_inward_supply_query(["action", "doc_type"])

        if name:
            query = query.where(self.IMS_RECONCILER.inward_supply.name == name)

        query = self.IMS_RECONCILER.get_query_with_filters(
            self.IMS_RECONCILER.inward_supply, query, filters
        )

        return query.run(as_dict=True)

    def get_all_purchases(self, name=None, filters=None):
        if not filters:
            filters = {}

        purchases = self.get_all_purchase_invoice(name, filters)

        return {doc.name: doc for doc in purchases}

    def get_all_purchase_invoice(self, name, filters):
        query = self.IMS_RECONCILER.get_base_purchase_query()

        if name:
            query = query.where(self.IMS_RECONCILER.purchase_invoice.name == name)

        query = self.IMS_RECONCILER.get_query_with_filters(
            self.IMS_RECONCILER.purchase_invoice, query, filters
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
    frappe.has_permission("GST Return Log", "write", throw=True)

    ims_log = frappe.get_doc(
        "GST Return Log",
        f"IMS-{company_gstin}",
    )

    json_data = get_data(company_gstin)

    if not json_data:
        return

    verify_request_in_progress(ims_log)

    # Make API Request
    api = IMSAPI(company_gstin)
    response = api.save_ims_action(json_data)
    update_return_log(ims_log, response.get("reference_id"), "upload", api.request_id)


@frappe.whitelist()
@otp_handler
def check_action_status(company_gstin):
    frappe.has_permission("GST Return Log", "write", throw=True)

    ims_log = frappe.get_doc(
        "GST Return Log",
        f"IMS-{company_gstin}",
    )

    return process_upload_ims(ims_log)


def reset_invoices(company_gstin):
    frappe.has_permission("GST Return Log", "write", throw=True)

    ims_log = frappe.get_doc(
        "GST Return Log",
        f"IMS-{company_gstin}",
    )

    json_data = get_data(company_gstin, is_reset=True)

    verify_request_in_progress(ims_log)

    api = IMSAPI(company_gstin)
    response = api.reset_ims_action(json_data)

    update_return_log(ims_log, response.get("reference_id"), "reset", api.request_id)


def get_data(company_gstin, is_reset=False):
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
        query.where(IfNull(ims_reconciler.inward_supply.ims_action, "") != "")
        .where(IfNull(ims_reconciler.inward_supply.previous_ims_action, "") != "")
        .where(
            ims_reconciler.inward_supply.ims_action
            != ims_reconciler.inward_supply.previous_ims_action
        )
        .where(ims_reconciler.inward_supply.gstr_1_filled == 1)
        .run(as_dict=True)
    )

    json_data = convert_data_to_gov_format(
        gst_inward_supply_list, company_gstin, is_reset
    )

    return json_data


def convert_data_to_gov_format(gst_inward_supply_list, company_gstin, is_reset=False):
    category_key_map = {
        "Invoice_0": "b2b",
        "Invoice_1": "b2ba",
        "Debit Note_0": "dn",
        "Debit Note_1": "dna",
        "Credit Note_0": "cn",
        "Credit Note_1": "cna",
    }

    json_data = {}
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
        result = []

        for invoice in invoices:
            data = {
                "stin": invoice.supplier_gstin,
                # "inv_typ": invoice.supply_type, TODO: Check options
                "srcform": "",
                "rtnprd": invoice.sup_return_period,
                "val": invoice.document_value,
                "pos": STATE_NUMBERS[invoice.place_of_supply.split("-")[1]],
                "prev_status": invoice.previous_ims_action,
                "iamt": invoice.igst,
                "camt": invoice.cgst,
                "samt": invoice.sgst,
                "cess": invoice.cess,
                "txval": invoice.taxable_value,
                **_class.get_category_details(invoice),
            }

            if not is_reset:
                data.update(
                    {
                        "action": invoice.ims_action,
                    }
                )

            result.append(data)

        json_data[category] = data

    return json_data


def update_return_log(doc, token, request_id, action, status=None):
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
        return

    response = api.get_request_status(doc.token)
    status_cd = response.get("status_cd")

    if status_cd != "IP":
        doc.db_set({"status": status_code_map.get(status_cd)})
        # TODO: Enqueue Notification

    if status_cd == "PE":
        response["error_report"] = get_error_list(response.get("error_report"))

    if status_cd == "P":
        # TODO: Update Previous IMS Action
        pass

    return response


def get_error_list(report):
    error_report = []
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

    return error_report
