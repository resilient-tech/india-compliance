# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

from enum import Enum
from itertools import chain

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.custom import ConstantColumn

TAX_FIELDS = (
    "igst_amount",
    "cgst_amount",
    "sgst_amount",
    "cess_amount",
)


def execute(filters: dict | None = None) -> tuple[list[dict], list[dict]]:
    report = ITCAvailed(filters)
    return report.get_columns(), report.get_data()


class ITCAvailedCategory(Enum):
    INWARD_DOMESTIC = "Inward supplies (other than imports and inward supplies liable to reverse charge but includes services received from SEZs)"

    UNREG_RCM = "Inward supplies received from unregistered persons liable to reverse charge (other than A above) on which tax is paid & ITC availed"

    REG_RCM = "Inward supplies received from registered persons liable to reverse charge (other than A above) on which tax is paid & ITC availed"

    IMPORT_GOODS = "Import Of Goods (including supplies from SEZ)"

    IMPORT_SERVICES = "Import Of Services (excluding inward supplies from SEZ)"

    ITC_FROM_ISD = "Input Tax credit received from ISD"

    @property
    def title(self) -> str:
        return self.value

    @property
    def has_subcategory(self) -> bool:
        return bool(ITC_AVAILED_CATEGORY_MAPPING.get(self))


class ITCAvailedSubCategory:
    INPUTS = "Inputs"
    CAPITAL_GOODS = "Capital Goods"
    INPUT_SERVICES = "Input Services"


ITC_AVAILED_CATEGORY_MAPPING = {
    ITCAvailedCategory.INWARD_DOMESTIC: [
        ITCAvailedSubCategory.INPUTS,
        ITCAvailedSubCategory.CAPITAL_GOODS,
        ITCAvailedSubCategory.INPUT_SERVICES,
    ],
    ITCAvailedCategory.UNREG_RCM: [
        ITCAvailedSubCategory.INPUTS,
        ITCAvailedSubCategory.CAPITAL_GOODS,
        ITCAvailedSubCategory.INPUT_SERVICES,
    ],
    ITCAvailedCategory.REG_RCM: [
        ITCAvailedSubCategory.INPUTS,
        ITCAvailedSubCategory.CAPITAL_GOODS,
        ITCAvailedSubCategory.INPUT_SERVICES,
    ],
    ITCAvailedCategory.IMPORT_GOODS: [
        ITCAvailedSubCategory.INPUTS,
        ITCAvailedSubCategory.CAPITAL_GOODS,
    ],
    ITCAvailedCategory.IMPORT_SERVICES: None,
    ITCAvailedCategory.ITC_FROM_ISD: None,
}


class ITCAvailedSummaryCategory:
    def get_category(self, row: dict) -> ITCAvailedCategory | None:
        gst_category = row.get("gst_category")
        itc_classification = row.get("itc_classification")
        is_reverse_charge = row.get("is_reverse_charge")

        if (
            gst_category != "Overseas"
            and not is_reverse_charge
            and itc_classification != "Input Service Distributor"
        ):
            return ITCAvailedCategory.INWARD_DOMESTIC

        elif gst_category == "Unregistered" and is_reverse_charge:
            return ITCAvailedCategory.UNREG_RCM

        elif gst_category != "Unregistered" and is_reverse_charge:
            return ITCAvailedCategory.REG_RCM

        elif itc_classification == "Import Of Goods":
            return ITCAvailedCategory.IMPORT_GOODS

        elif itc_classification == "Import Of Service":
            return ITCAvailedCategory.IMPORT_SERVICES

        elif itc_classification == "Input Service Distributor":
            return ITCAvailedCategory.ITC_FROM_ISD

        return None

    def get_subcategory(
        self, row: dict, category: ITCAvailedCategory
    ) -> ITCAvailedSubCategory | None:
        if not category or not category.has_subcategory:
            return None

        if row.get("is_fixed_asset") == 1:
            return ITCAvailedSubCategory.CAPITAL_GOODS

        elif (gst_hsn_code := row.get("gst_hsn_code")) and (
            gst_hsn_code.startswith("99")
        ):
            return ITCAvailedSubCategory.INPUT_SERVICES

        else:
            return ITCAvailedSubCategory.INPUTS


class ITCAvailedSummaryData:
    def _get_data(self, filters: dict) -> list[dict]:
        return chain(
            self._get_bill_of_entry_data(filters),
            self._get_purchase_invoice_data(filters),
        )

    def _get_purchase_invoice_data(self, filters: dict) -> list[dict]:
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
                doc_item.gst_hsn_code,
                doc_item.cgst_amount,
                doc_item.sgst_amount,
                doc_item.igst_amount,
                (doc_item.cess_amount + doc_item.cess_non_advol_amount).as_(
                    "cess_amount"
                ),
            )
            .where(
                (doc.docstatus == 1)
                & (doc.posting_date[filters.get("from_date") : filters.get("to_date")])
                & (doc.company == filters.get("company"))
                & (doc.company_gstin != doc.supplier_gstin)
                & (doc.is_opening == "No")
            )
        )

        if filters.get("company_gstin"):
            query = query.where(doc.company_gstin == filters.get("company_gstin"))

        return query.run(as_dict=True)

    def _get_bill_of_entry_data(self, filters: dict) -> list[dict]:
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
                doc_item.gst_hsn_code,
                doc_item.cgst_amount,
                doc_item.sgst_amount,
                doc_item.igst_amount,
                (doc_item.cess_amount + doc_item.cess_non_advol_amount).as_(
                    "cess_amount"
                ),
            )
            .where(
                (doc.docstatus == 1)
                & (doc.posting_date[filters.get("from_date") : filters.get("to_date")])
                & (doc.company == filters.get("company"))
            )
        )

        if filters.get("company_gstin"):
            query = query.where(doc.company_gstin == filters.get("company_gstin"))

        return query.run(as_dict=True)


class ITCAvailed(ITCAvailedSummaryCategory, ITCAvailedSummaryData):
    def __init__(self, filters: dict) -> None:
        filters.from_date, filters.to_date = filters.get("date_range")
        self.filters = filters

    def get_initial_summary(self) -> dict:
        _zero_taxes = {tax_field: 0 for tax_field in TAX_FIELDS}

        summary = {}

        for category, subcategories in ITC_AVAILED_CATEGORY_MAPPING.items():
            if subcategories:
                summary[category] = {
                    subcategory: _zero_taxes.copy() for subcategory in subcategories
                }
            else:
                summary[category] = _zero_taxes.copy()

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
        data = self._get_data(self.filters)

        summary = self.get_initial_summary()

        for row in data:
            category = self.get_category(row)
            if not category or not (_summary_dict := summary.get(category)):
                continue

            sub_category = self.get_subcategory(row, category)

            if not sub_category or not (
                _summary_dict := _summary_dict.get(sub_category)
            ):
                continue

            for tax_field in TAX_FIELDS:
                _summary_dict[tax_field] += row.get(tax_field, 0)

        return self._build_transformed_summary(summary)

    def _build_transformed_summary(self, summary: dict) -> list[dict]:
        transformed = []

        for idx, (category, _summary) in enumerate(summary.items()):
            letter = chr(65 + idx)  # 65 is 'A'
            title = category.title
            has_subcategory = category.has_subcategory

            transformed.append(
                self._create_entry(
                    f"{letter}) {title}",
                    self._aggregate_summary(_summary) if has_subcategory else _summary,
                    indent=0,
                )
            )

            if has_subcategory:
                for subcategory, sub_summary in _summary.items():
                    transformed.append(
                        self._create_entry(subcategory, sub_summary, indent=1)
                    )
            else:
                transformed.append(self._create_entry(title, _summary, indent=1))

        return transformed

    def _aggregate_summary(self, summary: dict) -> dict:
        totals = {tax_field: 0 for tax_field in TAX_FIELDS}

        for taxes in summary.values():
            for tax_field in TAX_FIELDS:
                totals[tax_field] += taxes.get(tax_field, 0)

        return totals

    def _create_entry(self, details: str, summary_data: dict, indent: int = 0) -> dict:
        return {
            "details": details,
            **summary_data,
            "indent": indent,
        }
