# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from india_compliance.gst_india.api_classes.taxpayer_base import (
    TaxpayerBaseAPI,
    otp_handler,
)
from india_compliance.gst_india.doctype.gst_invoice_management_system import (
    IMSReconciler,
    InwardSupply,
    PurchaseInvoice,
    process_upload_or_reset_ims,
)
from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    ReconciledData,
)
from india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_utils import (
    link_documents,
    unlink_documents,
)
from india_compliance.gst_india.utils.gstr_2 import (
    download_and_upload_ims_invoices,
    download_ims_invoices,
    upload_ims_invoices,
)


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

        inward_supplies = InwardSupply().get_all_inward_supplies(
            names=inward_supply, filters=filters
        )
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

        inward_supply = InwardSupply().get_all_inward_supplies(
            names=[inward_supply_name]
        )
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
@otp_handler
def download_invoices(company_gstin, company):
    frappe.has_permission("GST Invoice Management System", "write", throw=True)

    TaxpayerBaseAPI(company_gstin).validate_auth_token()

    frappe.enqueue(
        download_ims_invoices,
        queue="long",
        company_gstin=company_gstin,
        company=company,
    )


@frappe.whitelist()
@otp_handler
def upload_invoices(company_gstin):
    frappe.has_permission("GST Invoice Management System", "write", throw=True)
    frappe.has_permission("GST Return Log", "write", throw=True)

    return upload_ims_invoices(company_gstin)


@frappe.whitelist()
@otp_handler
def sync_with_gstn_and_reupload(company_gstin, company):
    frappe.has_permission("GST Invoice Management System", "write", throw=True)
    frappe.has_permission("GST Return Log", "write", throw=True)

    TaxpayerBaseAPI(company_gstin).validate_auth_token()

    frappe.enqueue(
        download_and_upload_ims_invoices,
        queue="long",
        company_gstin=company_gstin,
        company=company,
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
