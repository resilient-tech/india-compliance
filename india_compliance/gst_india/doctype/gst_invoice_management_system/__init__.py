import frappe
from frappe.query_builder import Case
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import Abs, IfNull, Sum

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    GSTIN_RULES,
    PAN_RULES,
    BaseUtil,
    PurchaseInvoice,
    Reconciler,
)


class IMSReconciler:
    ORIGINAL_VS_AMENDED = (
        {
            "original": "B2B",
            "amended": "B2BA",
        },
        {
            "original": "CDNR",
            "amended": "CDNRA",
        },
    )

    def __init__(self):
        self.inward_supply = frappe.qb.DocType("GST Inward Supply")
        self.purchase_invoice = frappe.qb.DocType("Purchase Invoice")
        self.purchase_invoice_item = frappe.qb.DocType("Purchase Invoice Item")
        self.boe = frappe.qb.DocType("Bill of Entry")
        self.boe_item = frappe.qb.DocType("Bill of Entry Item")

    def auto_reconcile_invoices(self, filters):
        """
        Reconcile purchases and inward supplies.
        """

        _Reconciler = Reconciler()

        for row in self.ORIGINAL_VS_AMENDED:
            filters["category"] = row["original"]
            filters["amended_category"] = row["amended"] or None
            _Reconciler.category = row["original"]

            purchases = self.get_unmatched_purchase_invoices(filters)
            inward_supplies = self.get_unmatched_inward_supplies(filters)

            # GSTIN Level matching
            _Reconciler.reconcile_for_rules(GSTIN_RULES, purchases, inward_supplies)

            # PAN Level matching
            purchases = _Reconciler.get_pan_level_data(purchases)
            inward_supplies = _Reconciler.get_pan_level_data(inward_supplies)
            _Reconciler.reconcile_for_rules(PAN_RULES, purchases, inward_supplies)

    def get_unmatched_inward_supplies(self, filters):
        categories = [filters.category, filters.amended_category]

        query = self.get_base_inward_supply_query()
        query = self.get_query_with_filters(self.inward_supply, query, filters)

        data = (
            query.where(IfNull(self.inward_supply.match_status, "") == "")
            .where(IfNull(self.inward_supply.previous_ims_action, "") != "")
            .where(self.inward_supply.classification.isin(categories))
            .run(as_dict=True)
        )

        for doc in data:
            doc.fy = BaseUtil.get_fy(doc.bill_date)

        return BaseUtil.get_dict_for_key("supplier_gstin", data)

    def get_unmatched_purchase_invoices(self, filters):
        gst_category = (
            ("Registered Regular", "Tax Deductor", "Input Service Distributor")
            if filters.category in ("B2B", "ISD")
            else ("SEZ", "Overseas", "UIN Holders")
        )

        query = self.get_base_purchase_query()
        query = self.get_query_with_filters(self.purchase_invoice, query, filters)

        data = (
            query.where(
                self.purchase_invoice.name.notin(
                    PurchaseInvoice.query_matched_purchase_invoice()
                )
            )
            .where(self.purchase_invoice.gst_category.isin(gst_category))
            .where(self.purchase_invoice.is_return == 0)
            .where(self.purchase_invoice.is_reverse_charge == 0)
            .run(as_dict=True)
        )

        for doc in data:
            doc.fy = BaseUtil.get_fy(doc.bill_date)

        return BaseUtil.get_dict_for_key("supplier_gstin", data)

    def get_base_inward_supply_query(self, additional_fields=None):
        fields = self.get_fields(
            additional_fields=additional_fields, table=self.inward_supply
        )

        return (
            frappe.qb.from_(self.inward_supply)
            .select(
                *fields,
                self.inward_supply.name,
                self.inward_supply.link_name,
                self.inward_supply.link_doctype,
                self.inward_supply.match_status,
                self.inward_supply.ims_action,
                self.inward_supply.previous_ims_action,
                self.inward_supply.supply_type,
                self.inward_supply.classification,
                self.inward_supply.is_pending_action_allowed,
                self.inward_supply.supplier_return_form,
                self.inward_supply.igst,
                self.inward_supply.cgst,
                self.inward_supply.sgst,
                self.inward_supply.cess,
                self.inward_supply.taxable_value,
                ConstantColumn("GST Inward Supply").as_("doctype"),
                Case()
                .when(
                    (
                        self.inward_supply.ims_action
                        == self.inward_supply.previous_ims_action
                    ),
                    False,
                )
                .else_(True)
                .as_("pending_upload"),
            )
            .where(IfNull(self.inward_supply.previous_ims_action, "") != "")
        )

    def get_base_purchase_query(self):
        fields = self.get_fields(
            table=self.purchase_invoice,
        )
        tax_fields = [
            self.query_tax_amount(self.purchase_invoice_item, f"{tax_type}_amount").as_(
                tax_type
            )
            for tax_type in GST_TAX_TYPES
        ]

        return (
            frappe.qb.from_(self.purchase_invoice)
            .left_join(self.purchase_invoice_item)
            .on(self.purchase_invoice_item.parent == self.purchase_invoice.name)
            .select(
                Abs(Sum(self.purchase_invoice_item.taxable_value)).as_("taxable_value"),
                *tax_fields,
                *fields,
                ConstantColumn("Purchase Invoice").as_("doctype"),
            )
            .groupby(self.purchase_invoice.name)
        )

    def get_query_with_filters(self, doc, query, filters):
        if filters.get("company"):
            query = query.where(doc.company == filters["company"])

        if filters.get("company_gstin"):
            query = query.where(doc.company_gstin == filters["company_gstin"])

        return query

    def get_fields(self, additional_fields=None, table=None):
        fields = [
            "supplier_gstin",
            "supplier_name",
            "bill_no",
            "bill_date",
            "name",
            "company",
            "company_gstin",
            "is_reverse_charge",
            "place_of_supply",
        ]

        if additional_fields:
            fields += additional_fields

        fields = [table[field] for field in fields]

        return fields

    def query_tax_amount(self, doc, field):
        return Abs(Sum(getattr(doc, field)))
