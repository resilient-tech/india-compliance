# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from india_compliance.gst_india.api_classes.taxpayer_base import (
    TaxpayerBaseAPI,
    otp_handler,
)
from india_compliance.gst_india.api_classes.taxpayer_returns import IMSAPI
from india_compliance.gst_india.doctype.gst_invoice_management_system import (
    IMSReconciler,
    InwardSupply,
    PurchaseInvoice,
)
from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    update_previous_ims_action as _update_previous_ims_action,
)
from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    enqueue_notification,
    set_gstr_actions,
    status_code_map,
    verify_request_in_progress,
)
from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    ReconciledData,
)
from india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_utils import (
    _get_link_options,
    link_documents,
    unlink_documents,
)
from india_compliance.gst_india.utils.gstr_2 import (
    GSTRCategory,
    download_ims_invoices,
    get_data_handler,
)
from india_compliance.gst_india.utils.gstr_utils import ReturnType


class GSTInvoiceManagementSystem(Document):
    @frappe.whitelist()
    def autoreconcile_and_get_data(self, inward_supply=None, purchase=None):
        frappe.has_permission("GST Invoice Management System", "write", throw=True)

        filters = frappe._dict(
            {
                "company": self.company,
                "company_gstin": self.company_gstin,
            }
        )

        # Auto-Reconcile invoices
        IMSReconciler().auto_reconcile_invoices(filters)

        return self.get_invoice_data(inward_supply, purchase, filters)

    def get_invoice_data(self, inward_supply=None, purchase=None, filters=None):
        if not filters:
            filters = frappe._dict(
                {
                    "company": self.company,
                    "company_gstin": self.company_gstin,
                }
            )

        inward_supplies = InwardSupply(
            company_gstin=self.company_gstin
        ).get_all_inward_supplies(names=inward_supply)
        purchases = PurchaseInvoice().get_all_purchases(names=purchase, filters=filters)

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

        inward_supply = InwardSupply(
            company_gstin=self.company_gstin
        ).get_all_inward_supplies(names=[inward_supply_name])
        purchases = PurchaseInvoice().get_all_purchases(names=[purchase_name])

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

    @frappe.whitelist()
    def get_link_options(self, filters):
        frappe.has_permission("GST Invoice Management System", "write", throw=True)

        if isinstance(filters, dict):
            filters = frappe._dict(filters)

        PI = frappe.qb.DocType("Purchase Invoice")
        query = (
            PurchaseInvoice()
            .get_base_purchase_query(["gst_category", "is_return"])
            .where(PI.supplier_gstin.like(f"%{filters.supplier_gstin}%"))
            .where(PI.bill_date[filters.bill_from_date : filters.bill_to_date])
        )

        if not filters.show_matched:
            query = query.where(PI.reconciliation_status == "Unreconciled")

        return _get_link_options(query.run(as_dict=True))


@frappe.whitelist()
@otp_handler
def download_invoices(company_gstin):
    frappe.has_permission("GST Invoice Management System", "write", throw=True)

    TaxpayerBaseAPI(company_gstin).validate_auth_token()

    frappe.enqueue(
        download_ims_invoices,
        queue="long",
        gstin=company_gstin,
    )


@frappe.whitelist()
@otp_handler
def upload_invoices(company_gstin):
    frappe.has_permission("GST Invoice Management System", "write", throw=True)
    frappe.has_permission("GST Return Log", "write", throw=True)

    return upload_ims_invoices(company_gstin)


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

    return process_upload_or_reset_ims(ims_log, action)


def upload_ims_invoices(company_gstin):
    if not frappe.db.exists("GST Return Log", f"IMS-ALL-{company_gstin}"):
        frappe.throw(_("Please download invoices before uploading"))
        return

    ims_log = frappe.get_doc(
        "GST Return Log",
        f"IMS-ALL-{company_gstin}",
    )

    upload_data, reset_data = get_data_for_upload(company_gstin)

    if not (upload_data or reset_data):
        return False

    verify_request_in_progress(ims_log, False)

    api = IMSAPI(company_gstin)

    if upload_data:
        # Upload invoices where action in ["Accepted", "Rejected", "Pending"]
        response = api.save_ims_action(upload_data)
        set_gstr_actions(
            ims_log, "upload", response.get("reference_id"), api.request_id
        )

    if reset_data:
        # Reset invoices where action is "No Action"
        response = api.reset_ims_action(reset_data)
        set_gstr_actions(ims_log, "reset", response.get("reference_id"), api.request_id)

    return True


def download_and_upload_ims_invoices(company_gstin):
    """
    1. This function will download invoices from GST Portal,
       and if there are some queued invoices then upload will be skipped.

    2. If there are no queued invoices, then it will upload the invoices to GST Portal.

    3. It will check the status regardless of whether any data was uploaded or not.
       (To notify user that process is completed successfully).
    """

    has_queued_invoices = download_ims_invoices(company_gstin)

    # TODO: flag for pending upload and cron job for queued invoices
    if has_queued_invoices:
        return

    upload_ims_invoices(company_gstin)

    frappe.publish_realtime(
        "check_ims_upload_status",
        user=frappe.session.user,
    )


def get_data_for_upload(company_gstin):
    category_key_map = {
        "Invoice_0": GSTRCategory.B2B.value,
        "Invoice_1": GSTRCategory.B2BA.value,
        "Debit Note_0": GSTRCategory.B2BDN.value,
        "Debit Note_1": GSTRCategory.B2BDNA.value,
        "Credit Note_0": GSTRCategory.B2BCN.value,
        "Credit Note_1": GSTRCategory.B2BCNA.value,
    }

    upload_data = {}
    reset_data = {}
    key_invoice_map = {}

    gst_inward_supply_list = get_inward_supplies_to_upload(company_gstin)

    for invoice in gst_inward_supply_list:
        key = f"{invoice.doc_type}_{invoice.is_amended}"
        key_invoice_map.setdefault(key, []).append(invoice)

    for key, invoices in key_invoice_map.items():
        category = category_key_map[key]
        _class = get_data_handler(ReturnType.IMS.value, category)()
        upload_invoices = []
        reset_invoices = []

        for invoice in invoices:
            data = {
                **_class.convert_data_to_gov_format(invoice),
                **_class.get_category_details(invoice),
            }

            if invoice.ims_action != "No Action":
                upload_invoices.append(data)
            else:
                reset_invoices.append(data)

        if upload_invoices:
            upload_data[category.lower()] = upload_invoices

        if reset_invoices:
            reset_data[category.lower()] = reset_invoices

    return upload_data, reset_data


def get_inward_supplies_to_upload(company_gstin):
    _InwardSupply = InwardSupply(company_gstin=company_gstin)
    query = _InwardSupply.get_base_inward_supply_query(
        additional_fields=[
            "doc_type",
            "is_amended",
            "sup_return_period",
            "document_value",
        ]
    )
    return query.where(
        _InwardSupply.inward_supply.ims_action
        != _InwardSupply.inward_supply.previous_ims_action
    ).run(as_dict=True)


def process_upload_or_reset_ims(return_log, action):
    response = {"status_cd": "P"}  # dummy_response
    if not return_log.actions:
        return response

    api = IMSAPI(return_log.gstin)

    doc = return_log.get_unprocessed_action(action)
    if not doc:
        return response

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
        erroneous_invoices = get_erroneous_invoices(response.get("error_report"))

    if status_cd in ["P", "PE"]:
        # Exclude erroneous invoices from previous IMS action update
        # This is enqueued because linking of integration request is enqueued
        # TODO: flag for re-upload?
        frappe.enqueue(
            update_previous_ims_action,
            queue="long",
            return_log=doc,
            erroneous_invoices=erroneous_invoices,
        )

    return response


def get_erroneous_invoices(error_report):
    invoice_names = []
    for error_list in error_report.values():
        for error in error_list:
            for invoice in error.get("inv"):
                invoice_names.append(f"{invoice.get('inum')}_{error.get('stin')}")

    return invoice_names


def get_uploaded_invoices(integration_request):
    request_data = frappe.parse_json(
        frappe.db.get_value(
            "Integration Request", {"name": integration_request}, "data"
        )
    )

    return request_data["body"]["data"]["invdata"]


def update_previous_ims_action(return_log, erroneous_invoices):
    from india_compliance.gst_india.utils.gstr_2 import ReturnType, get_data_handler

    integration_request = return_log.integration_request
    uploded_invoices = get_uploaded_invoices(integration_request)

    invoices_to_update = []
    for category, invoices in uploded_invoices.items():
        _class = get_data_handler(ReturnType.IMS.value, category.upper())
        invoices_to_update.extend(_class.get_all_transactions(invoices))

    for invoice in invoices_to_update:
        if f"{invoice.bill_no}_{invoice.supplier_gstin}" in erroneous_invoices:
            continue

        _update_previous_ims_action(invoice)
