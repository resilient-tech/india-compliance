# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_date_str, get_first_day, get_last_day

from india_compliance.gst_india.api_classes.taxpayer_base import otp_handler
from india_compliance.gst_india.api_classes.taxpayer_returns import IMSAPI
from india_compliance.gst_india.doctype.gstr_3b_beta import IMSReconciler
from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    ReconciledData,
)
from india_compliance.gst_india.utils import get_month_or_quarter_dict, ims


class GSTR3BBeta(Document):
    IMS_RECONCILER = IMSReconciler()

    @frappe.whitelist()
    def get_invoice_data(self):
        frappe.has_permission("GSTR-3B Beta", "write", throw=True)

        filters = self.get_filters()

        inward_supplies = self.get_all_inward_supplies(filters=filters)
        purchases_and_bill_of_entry = self.get_all_purchases(filters=filters)

        invoice_data = []
        for doc in inward_supplies:
            invoice_data.append(
                frappe._dict(
                    {
                        "ims_action": doc.ims_action,
                        "_inward_supply": doc,
                        "_purchase_invoice": purchases_and_bill_of_entry.pop(
                            doc.link_name, frappe._dict()
                        ),
                    }
                )
            )

        ReconciledData().process_data(invoice_data, retain_doc=True)

        return invoice_data

    @frappe.whitelist()
    def update_action(self, invoice_names, action):
        frappe.has_permission("GSTR-3B Beta", "write", throw=True)

        invoice_names = frappe.parse_json(invoice_names)

        self.update_previous_action(invoice_names)

        frappe.db.set_value(
            "GST Inward Supply",
            {"name": ("in", invoice_names)},
            "ims_action",
            action,
        )

    def update_previous_action(self, invoice_names):
        inward_supply = frappe.qb.DocType("GST Inward Supply")
        (
            frappe.qb.update(inward_supply)
            .set(inward_supply.previous_ims_action, inward_supply.ims_action)
            .where(inward_supply.name.isin(invoice_names))
            .run()
        )

    @frappe.whitelist()
    def get_invoice_comparision(self, purchase_name, inward_supply_name):
        frappe.has_permission("GSTR-3B Beta", "write", throw=True)

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

        query = self.IMS_RECONCILER.get_base_inward_supply_query()

        if name:
            query = query.where(self.IMS_RECONCILER.inward_supply.name == name)

        query = self.IMS_RECONCILER.get_query_with_filters(
            self.IMS_RECONCILER.inward_supply, query, filters
        )

        if filters.get("from_date"):
            query = query.where(
                self.IMS_RECONCILER.inward_supply.bill_date.between(
                    filters.from_date, filters.to_date
                )
            )

        return query.run(as_dict=True)

    def get_all_purchases(self, name=None, filters=None):
        if not filters:
            filters = {}

        purchases = self.get_all_purchase_invoice(name, filters)
        purchases.extend(self.get_all_bill_of_entry(name, filters))

        return {doc.name: doc for doc in purchases}

    def get_all_purchase_invoice(self, name, filters):
        query = self.IMS_RECONCILER.get_base_purchase_query()

        if name:
            query = query.where(self.IMS_RECONCILER.purchase_invoice.name == name)

        query = self.IMS_RECONCILER.get_query_with_filters(
            self.IMS_RECONCILER.purchase_invoice, query, filters
        )

        if filters.get("from_date"):
            query = query.where(
                self.IMS_RECONCILER.purchase_invoice.posting_date.between(
                    filters.from_date, filters.to_date
                )
            )

        return query.run(as_dict=True)

    def get_all_bill_of_entry(self, name, filters):
        query = self.IMS_RECONCILER.get_base_bill_of_entry_query()

        if name:
            query = query.where(self.IMS_RECONCILER.boe.name == name)

        query = self.IMS_RECONCILER.get_query_with_filters(
            self.IMS_RECONCILER.boe, query, filters
        )

        if filters.get("from_date"):
            query = query.where(
                self.IMS_RECONCILER.boe.bill_of_entry_date.between(
                    filters.from_date, filters.to_date
                )
            )

        return query.run(as_dict=True)

    def get_filters(self):
        month = get_month_or_quarter_dict().get(self.month)
        return frappe._dict(
            {
                "company": self.company,
                "company_gstin": self.company_gstin,
                "from_date": get_date_str(get_first_day(f"{self.year}-{month}-01")),
                "to_date": get_date_str(get_last_day(f"{self.year}-{month}-01")),
                "period": str(month).zfill(2) + str(self.year),
            }
        )


CATEGORIES = [
    "B2B",
    "B2BA",
    "B2BDN",
    "B2BDNA",
    "B2BCN",
    "B2BCNA",
]


@frappe.whitelist()
@otp_handler
def download_invoices_and_reconcile(company, company_gstin):
    frappe.has_permission("GSTR-3B Beta", "write", throw=True)

    api = IMSAPI(company_gstin)
    response = api.get_data(
        "GETINV", params={"section": ["B2B", "B2BA", "CN", "DN", "CNA", "DNA"]}
    )  # section is a list

    if response.error_type == "no_docs_found":
        return

    for category in CATEGORIES:
        getattr(ims, category)(company, company_gstin).create_transactions(
            response.get(category.lower(), [])
        )

    # Auto_Reconcile Invoices
    filters = frappe._dict({"company": company, "company_gstin": company_gstin})
    IMSReconciler().auto_reconcile_invoices(filters)
