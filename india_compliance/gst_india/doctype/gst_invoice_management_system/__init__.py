import frappe
from frappe.query_builder import Case
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import Abs, IfNull, Sum

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    GSTIN_RULES,
    PAN_RULES,
    BaseUtil,
    Reconciler,
)


class IMSReconciler(Reconciler):
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

    def auto_reconcile_invoices(self, filters):
        """
        Reconcile purchases and inward supplies.
        """
        for row in self.ORIGINAL_VS_AMENDED:
            filters.update(row)
            self.category = row["original"]

            purchases = PurchaseInvoice().get_unmatched_purchase_invoices(filters)
            inward_supplies = InwardSupply().get_unmatched_inward_supplies(filters)

            # GSTIN Level matching
            self.reconcile_for_rules(GSTIN_RULES, purchases, inward_supplies)

            # PAN Level matching
            purchases = self.get_pan_level_data(purchases)
            inward_supplies = self.get_pan_level_data(inward_supplies)
            self.reconcile_for_rules(PAN_RULES, purchases, inward_supplies)


class InwardSupply:
    def __init__(self, **kwargs):
        self.inward_supply = frappe.qb.DocType("GST Inward Supply")

    def get_all_inward_supplies(self, names=None, filters=None):
        if not filters:
            filters = {}

        query = self.get_base_inward_supply_query(["action", "doc_type"])

        if names:
            query = query.where(self.inward_supply.name.isin(names))

        query = get_query_with_filters(self.inward_supply, query, filters)

        return query.run(as_dict=True)

    def get_unmatched_inward_supplies(self, filters):
        categories = [filters["original"], filters["amended"]]

        query = self.get_base_inward_supply_query()
        query = get_query_with_filters(self.inward_supply, query, filters)

        data = (
            query.where(IfNull(self.inward_supply.match_status, "") == "")
            .where(self.inward_supply.classification.isin(categories))
            .run(as_dict=True)
        )

        for doc in data:
            doc.fy = BaseUtil.get_fy(doc.bill_date)

        return BaseUtil.get_dict_for_key("supplier_gstin", data)

    def get_base_inward_supply_query(self, additional_fields=None):
        fields = self.get_fields(additional_fields=additional_fields)

        return (
            frappe.qb.from_(self.inward_supply)
            .select(
                *fields,
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

    def get_fields(self, additional_fields=None):
        fields = [
            "supplier_gstin",
            "supplier_name",
            "company_gstin",
            "bill_no",
            "bill_date",
            "name",
            "is_reverse_charge",
            "place_of_supply",
            "link_name",
            "link_doctype",
            "match_status",
            "ims_action",
            "previous_ims_action",
            "supply_type",
            "classification",
            "is_pending_action_allowed",
            "supplier_return_form",
        ]

        if additional_fields:
            fields += additional_fields

        fields = [self.inward_supply[field] for field in fields]
        fields += self.get_tax_fields()

        return fields

    def get_tax_fields(self):
        fields = GST_TAX_TYPES[:-1] + ("taxable_value",)
        return [self.inward_supply[field] for field in fields]


class PurchaseInvoice:
    def __init__(self):
        self.purchase_invoice = frappe.qb.DocType("Purchase Invoice")
        self.purchase_invoice_item = frappe.qb.DocType("Purchase Invoice Item")

    def get_all_purchases(self, names=None, filters=None):
        if not filters:
            filters = {}

        query = self.get_base_purchase_query()

        if names:
            query = query.where(self.purchase_invoice.name.isin(names))

        query = get_query_with_filters(self.purchase_invoice, query, filters)

        purchases = query.run(as_dict=True)

        return {doc.name: doc for doc in purchases}

    def get_unmatched_purchase_invoices(self, filters):
        gst_category = (
            "Registered Regular",
            "Tax Deductor",
            "Input Service Distributor",
        )

        query = self.get_base_purchase_query()
        query = get_query_with_filters(self.purchase_invoice, query, filters)

        data = (
            query.where(self.purchase_invoice.gst_category.isin(gst_category))
            .where(self.purchase_invoice.reconciliation_status == "Unreconciled")
            .where(self.purchase_invoice.is_return == 0)
            .where(self.purchase_invoice.is_reverse_charge == 0)
            .run(as_dict=True)
        )

        for doc in data:
            doc.fy = BaseUtil.get_fy(doc.bill_date)

        return BaseUtil.get_dict_for_key("supplier_gstin", data)

    def get_base_purchase_query(self):
        fields = self.get_fields()

        return (
            frappe.qb.from_(self.purchase_invoice)
            .left_join(self.purchase_invoice_item)
            .on(self.purchase_invoice_item.parent == self.purchase_invoice.name)
            .select(
                Abs(Sum(self.purchase_invoice_item.taxable_value)).as_("taxable_value"),
                *fields,
                ConstantColumn("Purchase Invoice").as_("doctype"),
            )
            .groupby(self.purchase_invoice.name)
        )

    def get_fields(self, additional_fields=None):
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

        fields = [self.purchase_invoice[field] for field in fields]
        fields += self.get_tax_fields()

        return fields

    def get_tax_fields(self):
        return [
            query_tax_amount(self.purchase_invoice_item, f"{tax_type}_amount").as_(
                tax_type
            )
            for tax_type in GST_TAX_TYPES
        ]


def get_query_with_filters(doc, query, filters):
    if filters.get("company"):
        query = query.where(doc.company == filters["company"])

    if filters.get("company_gstin"):
        query = query.where(doc.company_gstin == filters["company_gstin"])

    return query


def query_tax_amount(doc, field):
    return Abs(Sum(getattr(doc, field)))
