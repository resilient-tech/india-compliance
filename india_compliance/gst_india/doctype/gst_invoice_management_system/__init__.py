import frappe
from frappe.query_builder import Case
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import Abs, IfNull, Sum
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
    get_accounting_dimensions,
)

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    GSTIN_RULES,
    PAN_RULES,
    BaseUtil,
    Reconciler,
)


class IMSReconciler(Reconciler):
    CATEGORIES = (
        {"doc_type": "Invoice", "category": "B2B"},
        {"doc_type": "Debit Note", "category": "CDNR"},
        {"doc_type": "Credit Note", "category": "CDNR"},
    )

    def reconcile(self, filters):
        """
        Reconcile purchases and inward supplies.
        """
        for row in self.CATEGORIES:
            filters["doc_type"], self.category = row.values()

            purchases = PurchaseInvoice().get_unmatched(filters)
            inward_supplies = InwardSupply().get_unmatched(filters)

            # GSTIN Level matching
            self.reconcile_for_rules(GSTIN_RULES, purchases, inward_supplies)

            # PAN Level matching
            purchases = self.get_pan_level_data(purchases)
            inward_supplies = self.get_pan_level_data(inward_supplies)
            self.reconcile_for_rules(PAN_RULES, purchases, inward_supplies)


class InwardSupply:
    def __init__(self):
        self.IMS = frappe.qb.DocType("GST Inward Supply")

    def get_all(self, company_gstin, names=None):
        query = self.get_query(company_gstin, ["action", "doc_type"])

        if names:
            query = query.where(self.IMS.name.isin(names))

        return query.run(as_dict=True)

    def get_for_save(self, company_gstin):
        return (
            self.get_query_for_upload(company_gstin)
            .where(self.IMS.ims_action != "No Action")
            .run(as_dict=True)
        )

    def get_for_reset(self, company_gstin):
        return (
            self.get_query_for_upload(company_gstin)
            .where(self.IMS.ims_action == "No Action")
            .run(as_dict=True)
        )

    def get_query_for_upload(self, company_gstin):
        return self.get_query(
            company_gstin,
            additional_fields=[
                "doc_type",
                "is_amended",
                "sup_return_period",
                "document_value",
            ],
        ).where(self.IMS.ims_action != self.IMS.previous_ims_action)

    def get_unmatched(self, filters):
        query = self.get_query(filters.company_gstin)
        data = (
            query.where(IfNull(self.IMS.match_status, "") == "")
            .where(self.IMS.doc_type == filters.doc_type)
            .run(as_dict=True)
        )

        for doc in data:
            doc.fy = BaseUtil.get_fy(doc.bill_date)

        return BaseUtil.get_dict_for_key("supplier_gstin", data)

    def get_query(self, company_gstin, additional_fields=None):
        fields = self.get_fields(additional_fields=additional_fields)

        return (
            frappe.qb.from_(self.IMS)
            .select(
                *fields,
                ConstantColumn("GST Inward Supply").as_("doctype"),
                Case()
                .when(
                    (self.IMS.ims_action == self.IMS.previous_ims_action),
                    False,
                )
                .else_(True)
                .as_("pending_upload"),
            )
            .where(IfNull(self.IMS.previous_ims_action, "") != "")
            .where(self.IMS.company_gstin == company_gstin)
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
            "is_supplier_return_filed",
        ]

        if additional_fields:
            fields += additional_fields

        fields = [self.IMS[field] for field in fields]
        fields += self.get_tax_fields()

        return fields

    def get_tax_fields(self):
        fields = GST_TAX_TYPES[:-1] + ("taxable_value",)
        return [self.IMS[field] for field in fields]


class PurchaseInvoice:
    def __init__(self):
        self.PI = frappe.qb.DocType("Purchase Invoice")
        self.PI_ITEM = frappe.qb.DocType("Purchase Invoice Item")

    def get_all(self, names=None, filters=None):
        dimension_fields = get_accounting_dimensions() + ["cost_center", "project"]
        additional_fields = dimension_fields + ["posting_date"]

        query = self.get_query(filters=filters, additional_fields=additional_fields)

        if names:
            query = query.where(self.PI.name.isin(names))

        purchases = query.run(as_dict=True)

        return {doc.name: doc for doc in purchases}

    def get_unmatched(self, filters):
        gst_category = (
            "Registered Regular",
            "Tax Deductor",
            "Tax Collector",
            "Input Service Distributor",
        )
        is_return = 1 if filters.doc_type == "Credit Note" else 0

        data = (
            self.get_query(filters=filters, is_return=is_return)
            .where(self.PI.gst_category.isin(gst_category))
            .where(self.PI.reconciliation_status == "Unreconciled")
            .where(self.PI.is_return == is_return)
            .where(self.PI.ineligibility_reason != "ITC restricted due to PoS rules")
            .run(as_dict=True)
        )

        for doc in data:
            doc.fy = BaseUtil.get_fy(doc.bill_date)

        return BaseUtil.get_dict_for_key("supplier_gstin", data)

    def get_query(self, filters=None, additional_fields=None, is_return=False):
        fields = self.get_fields(additional_fields, is_return)

        query = (
            frappe.qb.from_(self.PI)
            .left_join(self.PI_ITEM)
            .on(self.PI_ITEM.parent == self.PI.name)
            .select(
                Abs(Sum(self.PI_ITEM.taxable_value)).as_("taxable_value"),
                *fields,
                ConstantColumn("Purchase Invoice").as_("doctype"),
            )
            .where(self.PI.docstatus == 1)
            .where(IfNull(self.PI.reconciliation_status, "") != "Not Applicable")
            .where(self.PI.is_opening == "No")
            .where(self.PI_ITEM.parenttype == "Purchase Invoice")
            .where(self.PI.is_reverse_charge == 0)  # for IMS
            .groupby(self.PI.name)
        )

        if filters:
            query = self.apply_filters(query, filters)

        return query

    def apply_filters(self, query, filters):
        if filters.get("company"):
            query = query.where(self.PI.company == filters.company)

        if filters.get("company_gstin"):
            query = query.where(self.PI.company_gstin == filters.company_gstin)

        return query

    def get_fields(self, additional_fields=None, is_return=False):
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

        fields = [self.PI[field] for field in fields]
        fields += self.get_tax_fields()

        if is_return:
            # return is initiated by the customer. So bill date may not be available or known.
            fields += [self.PI.posting_date.as_("bill_date")]
        else:
            fields += [
                # Default to posting date if bill date is not available.
                Case()
                .when(
                    IfNull(self.PI.bill_date, "") == "",
                    self.PI.posting_date,
                )
                .else_(self.PI.bill_date)
                .as_("bill_date")
            ]

        return fields

    def get_tax_fields(self):
        return [
            self.query_tax_amount(f"{tax_type}_amount").as_(tax_type)
            for tax_type in GST_TAX_TYPES
        ]

    def query_tax_amount(self, field):
        return Abs(Sum(getattr(self.PI_ITEM, field)))
