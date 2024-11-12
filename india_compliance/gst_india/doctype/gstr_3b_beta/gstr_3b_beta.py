# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

# from collections import defaultdict

import frappe
from frappe.model.document import Document
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import Abs, Sum
from frappe.utils import get_date_str, get_first_day, get_last_day

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    ReconciledData,
)
from india_compliance.gst_india.utils import get_month_or_quarter_dict


@frappe.whitelist()
def get_comparision_data(purchase_name, inward_supply_name):
    GSTR3BBeta = frappe.get_doc("GSTR-3B Beta")
    return GSTR3BBeta.get_invoice_comparision(purchase_name, inward_supply_name)


class GSTR3BBeta(Document):
    @frappe.whitelist()
    def get_invoice_data(self):
        month = get_month_or_quarter_dict().get(self.month)
        filters = frappe._dict(
            {
                "company": self.company,
                "company_gstin": self.company_gstin,
                "from_date": get_date_str(get_first_day(f"{self.year}-{month}-01")),
                "to_date": get_date_str(get_last_day(f"{self.year}-{month}-01")),
            }
        )

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
        invoice_names = frappe.parse_json(invoice_names)

        self.update_previous_action(invoice_names)

        frappe.db.set_value(
            "GST Inward Supply",
            {"name": ("in", invoice_names)},
            "ims_action",
            action,
        )

    def update_previous_action(self, invoice_names):
        gst_inward_supply = frappe.qb.DocType("GST Inward Supply")
        (
            frappe.qb.update(gst_inward_supply)
            .set(gst_inward_supply.previous_ims_action, gst_inward_supply.ims_action)
            .where(gst_inward_supply.name.isin(invoice_names))
            .run()
        )

    def get_invoice_comparision(self, purchase_name, inward_supply_name):
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
                inward_supply.ims_action,
                inward_supply.supply_type,
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

        query = self.get_query_with_filters(inward_supply, query, filters)

        if filters.get("from_date"):
            query = query.where(
                inward_supply.bill_date.between(filters.from_date, filters.to_date)
            )

        return query.run(as_dict=True)

    def get_all_purchases(self, name=None, filters=None):
        if not filters:
            filters = {}

        purchases = self.get_all_purchase_invoice(name, filters)
        purchases.extend(self.get_all_bill_of_entry(name, filters))

        return {doc.name: doc for doc in purchases}

    def get_all_purchase_invoice(self, name, filters):
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

        query = self.get_query_with_filters(purchase, query, filters)

        if filters.get("from_date"):
            query = query.where(
                purchase.posting_date.between(filters.from_date, filters.to_date)
            )

        return query.run(as_dict=True)

    def get_all_bill_of_entry(self, name, filters):
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

        query = self.get_query_with_filters(boe, query, filters)

        if filters.get("from_date"):
            query = query.where(
                boe.bill_of_entry_date.between(filters.from_date, filters.to_date)
            )

        return query.run(as_dict=True)

    def query_tax_amount(self, doc, field):
        return Abs(Sum(getattr(doc, field)))

    def get_query_with_filters(self, doc, query, filters):
        if filters.get("company"):
            query = query.where(doc.company == filters.company)

        if filters.get("company_gstin"):
            query = query.where(doc.company_gstin == filters.company_gstin)

        return query
