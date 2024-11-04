# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe.model.document import Document
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import Abs, Sum

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    ReconciledData,
)


class GSTR3BBeta(Document):
    @frappe.whitelist()
    def fetch_invoice_data(self):
        inward_supplies = self.get_all_inward_supplies()

        invoice_data = {
            invoice["name"]: {
                "supplier_gstin": invoice["supplier_gstin"],
                "supplier": invoice["supplier_name"],
                "invoice_type": invoice["invoice_type"],
                "invoice_status": invoice["invoice_status"],
                "invoice_no": invoice["bill_no"],
                "invoice_name": invoice["name"],
                "invoice_date": invoice["bill_date"],
                "company": invoice["company"],
                "company_gstin": invoice["company_gstin"],
                "match_status": invoice["match_status"],
                "linked_doc": invoice["link_name"],
                "is_dirty": 0,
            }
            for invoice in inward_supplies
        }

        return invoice_data

    def before_save(self):
        invoices_to_update = defaultdict(set)
        for key, value in self.invoice_data.items():
            if value["is_dirty"]:
                invoices_to_update[value["invoice_status"]].add(key)

        self.update_invoice_status(invoices_to_update)

        self.invoice_data = ""

    def update_invoice_status(self, invoices_to_update):
        for action, invoices in invoices_to_update.items():
            frappe.db.set_value(
                "GST Inward Supply",
                {"name": ("in", invoices)},
                "invoice_status",
                action,
            )

    @frappe.whitelist()
    def get_invoice_details(self, purchase_name, inward_supply_name):
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

    def get_all_inward_supplies(self, name=None):
        inward_supply = frappe.qb.DocType("GST Inward Supply")
        inward_supply_item = frappe.qb.DocType("GST Inward Supply Item")
        fields = GST_TAX_TYPES[:-1] + ("taxable_value",)
        tax_fields = [Sum(inward_supply_item[field]).as_(field) for field in fields]

        query = (
            frappe.qb.from_(inward_supply)
            .left_join(inward_supply_item)
            .on(inward_supply_item.parent == inward_supply.name)
            .select(
                *tax_fields,
                inward_supply.supplier_gstin,
                inward_supply.supplier_name,
                inward_supply.bill_no,
                inward_supply.bill_date,
                inward_supply.company,
                inward_supply.company_gstin,
                inward_supply.link_name,
                inward_supply.link_doctype,
                inward_supply.match_status,
                inward_supply.invoice_status,
                inward_supply.invoice_type,
                inward_supply.name,
                inward_supply.classification,
                inward_supply.is_reverse_charge,
                inward_supply.place_of_supply,
                ConstantColumn("GST Inward Supply").as_("doctype"),
            )
            .where(inward_supply_item.parenttype == "GST Inward Supply")
            .groupby(inward_supply_item.parent)
        )

        if name:
            query = query.where(inward_supply.name == name)

        return query.run(as_dict=True)

    def get_all_purchases(self, name=None):
        purchases = self.get_all_purchase_invoice(name)
        purchases.extend(self.get_all_bill_of_entry(name))

        return {doc.name: doc for doc in purchases}

    def get_all_purchase_invoice(self, name=None):
        purchase = frappe.qb.DocType("Purchase Invoice")
        purchase_item = frappe.qb.DocType("Purchase Invoice Item")
        tax_fields = [
            self.query_tax_amount(purchase_item, f"{tax_type}_amount").as_(tax_type)
            for tax_type in GST_TAX_TYPES
        ]

        query = (
            frappe.qb.from_(purchase)
            .left_join(purchase_item)
            .on(purchase_item.parent == purchase.name)
            .select(
                Abs(Sum(purchase_item.taxable_value)).as_("taxable_value"),
                *tax_fields,
                purchase.name,
                purchase.supplier_gstin,
                purchase.supplier,
                purchase.bill_no,
                purchase.bill_date,
                purchase.company,
                purchase.company_gstin,
                purchase.is_reverse_charge,
                purchase.place_of_supply,
                ConstantColumn("Purchase Invoice").as_("doctype"),
            )
            .groupby(purchase.name)
        )

        if name:
            query = query.where(purchase.name == name)

        return query.run(as_dict=True)

    def get_all_bill_of_entry(self, name):
        boe = frappe.qb.DocType("Bill of Entry")
        boe_item = frappe.qb.DocType("Bill of Entry Item")
        purchase_invoice = frappe.qb.DocType("Purchase Invoice")

        tax_fields = [
            self.query_tax_amount(boe_item, f"{tax_type}_amount").as_(tax_type)
            for tax_type in GST_TAX_TYPES
        ]

        query = (
            frappe.qb.from_(boe)
            .left_join(boe_item)
            .on(boe_item.parent == boe.name)
            .join(purchase_invoice)
            .on(boe.purchase_invoice == purchase_invoice.name)
            .select(
                *tax_fields,
                boe.total_taxable_value.as_("taxable_value"),
                boe.bill_of_entry_no,
                boe.bill_of_entry_date,
                purchase_invoice.supplier_gstin,
                purchase_invoice.supplier,
                boe.name,
                purchase_invoice.is_reverse_charge,
                purchase_invoice.place_of_supply,
                ConstantColumn("Bill of Entry").as_("doctype"),
            )
            .where(boe.docstatus == 1)
            .where(boe_item.parenttype == "Bill of Entry")
            .groupby(boe.name)
        )

        if name:
            query = query.where(boe.name == name)

        return query.run(as_dict=True)

    def query_tax_amount(self, doc, field):
        return Abs(Sum(getattr(doc, field)))
