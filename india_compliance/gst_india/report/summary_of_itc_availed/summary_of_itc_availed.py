# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import IfNull

TAX_FIELDS = (
    "igst_amount",
    "cgst_amount",
    "sgst_amount",
    "cess_amount",
)


def execute(filters: dict | None = None) -> tuple[list[dict], list[dict]]:
    report = ITCAvailed(filters)
    return report.get_columns(), report.get_data()


class Category:
    INWARD_DOMESTIC = "Inward supplies (other than imports and inward supplies liable to reverse charge but includes services received from SEZs)"
    UNREG_RCM = "Inward supplies received from unregistered persons liable to reverse charge (other than A above) on which tax is paid & ITC availed"
    REG_RCM = "Inward supplies received from registered persons liable to reverse charge (other than A above) on which tax is paid & ITC availed"
    IMPORT_GOODS = "Import Of Goods (including supplies from SEZ)"
    IMPORT_SERVICES = "Import Of Services (excluding inward supplies from SEZ)"
    ITC_FROM_ISD = "Input Tax credit received from ISD"


class SubCategory:
    INPUTS = "Inputs"
    CAPITAL_GOODS = "Capital Goods"
    INPUT_SERVICES = "Input Services"


ITC_AVAILED_CATEGORY_MAPPING = {
    Category.INWARD_DOMESTIC: [
        SubCategory.INPUTS,
        SubCategory.CAPITAL_GOODS,
        SubCategory.INPUT_SERVICES,
    ],
    Category.UNREG_RCM: [
        SubCategory.INPUTS,
        SubCategory.CAPITAL_GOODS,
        SubCategory.INPUT_SERVICES,
    ],
    Category.REG_RCM: [
        SubCategory.INPUTS,
        SubCategory.CAPITAL_GOODS,
        SubCategory.INPUT_SERVICES,
    ],
    Category.IMPORT_GOODS: [
        SubCategory.INPUTS,
        SubCategory.CAPITAL_GOODS,
    ],
    Category.IMPORT_SERVICES: [Category.IMPORT_SERVICES],
    Category.ITC_FROM_ISD: [Category.ITC_FROM_ISD],
}


class ITCAvailedCategory:
    def get_category(self, row: dict) -> Category | None:
        gst_category = row.get("gst_category")
        itc_classification = row.get("itc_classification")
        is_reverse_charge = row.get("is_reverse_charge")

        if gst_category == "Unregistered" and is_reverse_charge:
            return Category.UNREG_RCM

        elif gst_category != "Unregistered" and is_reverse_charge:
            return Category.REG_RCM

        elif itc_classification == "Import Of Goods":
            return Category.IMPORT_GOODS

        elif itc_classification == "Import Of Service" and gst_category != "SEZ":
            return Category.IMPORT_SERVICES

        elif itc_classification == "Input Service Distributor":
            return Category.ITC_FROM_ISD

        return Category.INWARD_DOMESTIC

    def get_subcategory(self, row: dict, category: Category) -> SubCategory | None:
        # breakup not required
        if category in (Category.IMPORT_SERVICES, Category.ITC_FROM_ISD):
            return category

        elif row.get("is_fixed_asset") == 1:
            return SubCategory.CAPITAL_GOODS

        elif (row.get("gst_hsn_code") or "").startswith("99"):
            return SubCategory.INPUT_SERVICES

        return SubCategory.INPUTS


class ITCAvailedData:
    def __init__(self, filters: dict) -> None:
        filters = frappe._dict(filters or {})
        filters.from_date, filters.to_date = filters.date_range
        self.filters = filters

    def _get_data(self) -> list[dict]:
        return self._get_bill_of_entry_data() + self._get_purchase_invoice_data()

    def _get_purchase_invoice_data(self) -> list[dict]:
        doc = frappe.qb.DocType("Purchase Invoice")
        doc_item = frappe.qb.DocType("Purchase Invoice Item")

        query = (
            frappe.qb.from_(doc)
            .inner_join(doc_item)
            .on(doc.name == doc_item.parent)
            .select(
                doc.gst_category,
                doc.itc_classification,
                doc_item.is_fixed_asset,
                doc.is_reverse_charge,
            )
            .where(
                (doc.company_gstin != IfNull(doc.supplier_gstin, ""))
                & (doc.is_opening == "No")
            )
        )

        query = self._add_tax_fields_and_filters(query, doc, doc_item)

        return query.run(as_dict=True)

    def _get_bill_of_entry_data(self) -> list[dict]:
        doc = frappe.qb.DocType("Bill of Entry")
        item = frappe.qb.DocType("Item")
        doc_item = frappe.qb.DocType("Bill of Entry Item")

        query = (
            frappe.qb.from_(doc)
            .inner_join(doc_item)
            .on(doc.name == doc_item.parent)
            .inner_join(item)
            .on(doc_item.item_code == item.item_code)
            .select(
                Case("itc_classification")
                .when(doc_item.gst_hsn_code.like("99%"), "Import Of Service")
                .else_("Import Of Goods"),
                ConstantColumn("Overseas").as_("gst_category"),
                item.is_fixed_asset,
            )
        )

        query = self._add_tax_fields_and_filters(query, doc, doc_item)

        return query.run(as_dict=True)

    def _add_tax_fields_and_filters(self, query, doc, doc_item):
        query = query.select(
            doc_item.cgst_amount,
            doc_item.sgst_amount,
            doc_item.igst_amount,
            (doc_item.cess_amount + doc_item.cess_non_advol_amount).as_("cess_amount"),
        ).where(
            (doc.docstatus == 1)
            & (
                doc.posting_date[
                    self.filters.get("from_date") : self.filters.get("to_date")
                ]
            )
            & (doc.company == self.filters.get("company"))
        )

        if self.filters.get("company_gstin"):
            query = query.where(doc.company_gstin == self.filters.get("company_gstin"))

        return query


class ITCAvailed(ITCAvailedCategory, ITCAvailedData):
    def get_initial_summary(self) -> dict:
        summary = {}

        for category, subcategories in ITC_AVAILED_CATEGORY_MAPPING.items():
            summary[category] = {
                subcategory: defaultdict(float) for subcategory in subcategories
            }

        return summary

    def get_columns(self) -> list[dict]:
        return [
            {
                "label": _("Details"),
                "fieldname": "details",
                "fieldtype": "Data",
                "width": 1000,
            },
            {
                "label": _("Integrated tax (₹)"),
                "fieldname": "igst_amount",
                "fieldtype": "Currency",
                "width": 150,
            },
            {
                "label": _("Central tax (₹)"),
                "fieldname": "cgst_amount",
                "fieldtype": "Currency",
                "width": 150,
            },
            {
                "label": _("State/UT tax (₹)"),
                "fieldname": "sgst_amount",
                "fieldtype": "Currency",
                "width": 150,
            },
            {
                "label": _("Cess (₹)"),
                "fieldname": "cess_amount",
                "fieldtype": "Currency",
                "width": 150,
            },
        ]

    def get_data(self) -> list[dict]:
        data = self._get_data()

        summary = self.get_initial_summary()

        for row in data:
            category = self.get_category(row)
            sub_category = self.get_subcategory(row, category)

            if (_summary_dict := summary.get(category, {}).get(sub_category)) is None:
                continue

            for tax_field in TAX_FIELDS:
                _summary_dict[tax_field] += row.get(tax_field, 0)

        return self._build_transformed_summary(summary)

    def _build_transformed_summary(self, summary: dict) -> list[dict]:
        transformed = []

        for idx, (category, data) in enumerate(summary.items()):
            letter = chr(65 + idx)  # 65 is 'A'
            category = f"{letter}) {category}"

            # Category
            aggregate = self._aggregate_summary(data)
            transformed.append(dict(details=category, **aggregate, indent=0))

            # Subcategory
            for subcategory, sub_summary in data.items():
                transformed.append(dict(details=subcategory, **sub_summary, indent=1))

        return transformed

    def _aggregate_summary(self, summary: dict) -> dict:
        totals = defaultdict(float)

        for taxes in summary.values():
            for tax_field in TAX_FIELDS:
                totals[tax_field] += taxes.get(tax_field, 0)

        return totals
