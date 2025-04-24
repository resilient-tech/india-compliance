# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

from itertools import chain

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import LiteralValue

TAX_FIELDS = (
    "igst_amount",
    "cgst_amount",
    "sgst_amount",
    "cess_amount",
)


def execute(filters: dict | None = None) -> tuple[list[dict], list[dict]]:
    report = InwardSuppliesGSTSummary(filters)
    return report.get_columns(), report.get_data()


class InwardSuppliesGSTSummaryMapping:
    def __init__(self) -> None:
        self.mapping = {
            "A": {
                "title": "Inward supplies (other than imports and inward supplies liable to reverse charge but includes services received from SEZs)",
                "category": ...,
                "has_subcategory": True,
            },
            "B": {
                "title": "Inward supplies received from unregistered persons liable to reverse charge (other than A above) on which tax is paid & ITC availed",
                "category": ...,
                "has_subcategory": True,
            },
            "C": {
                "title": "Inward supplies received from registered persons liable to reverse charge (other than A above) on which tax is paid & ITC availed",
                "category": ...,
                "has_subcategory": True,
            },
            "D": {
                "title": "Import Of Goods (including supplies from SEZ)",
                "category": ...,
                "has_subcategory": True,
            },
            "E": {
                "title": "Import Of Services (excluding inward supplies from SEZ)",
                "category": ...,
                "has_subcategory": False,
            },
            "F": {
                "title": "Input Tax credit received from ISD",
                "category": ...,
                "has_subcategory": False,
            },
        }

    def get_title(self, category: str) -> str:
        return self.mapping.get(category, {}).get("title")

    def has_subcategory(self, category: str) -> bool:
        return self.mapping.get(category, {}).get("has_subcategory", False)


class InwardSuppliesGSTSummaryCategory(InwardSuppliesGSTSummaryMapping):
    def __init__(self) -> None:
        super().__init__()
        self.mapping["A"]["category"] = self._is_inward_supplies_from_registered
        self.mapping["B"]["category"] = self._is_inward_supplies_from_unregistered
        self.mapping["C"][
            "category"
        ] = self._is_inward_supplies_from_registered_reverse_charge
        self.mapping["D"]["category"] = self._is_import_of_goods_sez
        self.mapping["E"]["category"] = self._is_import_of_services
        self.mapping["F"]["category"] = self._is_itc_received_from_isd

    def _is_inward_supplies_from_registered(self, row: dict) -> bool:
        return (
            row.get("gst_category") != "Overseas"
            and not row.get("is_reverse_charge")
            and row.get("itc_classification") != "Input Service Distributor"
        )

    def _is_inward_supplies_from_unregistered(self, row: dict) -> bool:
        return row.get("gst_category") == "Unregistered" and row.get(
            "is_reverse_charge"
        )

    def _is_inward_supplies_from_registered_reverse_charge(self, row: dict) -> bool:
        return row.get("gst_category") != "Unregistered" and row.get(
            "is_reverse_charge"
        )

    def _is_import_of_goods_sez(self, row: dict) -> bool:
        return row.get("itc_classification") == "Import Of Goods"

    def _is_import_of_services(self, row: dict) -> bool:
        return row.get("itc_classification") == "Import Of Service"

    def _is_itc_received_from_isd(self, row: dict) -> bool:
        return row.get("itc_classification") == "Input Service Distributor"

    def get_category(self, row: dict) -> str:
        for detail_type, mapping in self.mapping.items():
            if (fn := mapping["category"]) and fn(row):
                return detail_type

    def get_subcategory(self, category: str, row: dict) -> str | None:
        if not self.has_subcategory(category):
            return None

        if row.get("is_fixed_asset") == 1:
            return "Capital Goods"

        if (gst_hsn_code := row.get("gst_hsn_code")) and (
            gst_hsn_code.startswith("99")
        ):
            return "Input Services"

        return "Inputs"


class InwardSuppliesGSTSummaryData:
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
                & (doc.posting_date[filters.from_date : filters.to_date])
                & (doc.company == filters.company)
                & (doc.company_gstin != doc.supplier_gstin)
                & (doc.is_opening == "No")
            )
        )

        if filters.get("company_gstin"):
            query = query.where(doc.company_gstin == filters.company_gstin)

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
                LiteralValue("'Overseas'").as_("gst_category"),
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
                & (doc.posting_date[filters.from_date : filters.to_date])
                & (doc.company == filters.company)
            )
        )

        if filters.get("company_gstin"):
            query = query.where(doc.company_gstin == filters.company_gstin)

        return query.run(as_dict=True)


class InwardSuppliesGSTSummary(
    InwardSuppliesGSTSummaryCategory, InwardSuppliesGSTSummaryData
):
    def __init__(self, filters: dict) -> None:
        super().__init__()
        filters.from_date, filters.to_date = filters.date_range
        self.filters = filters
        self._init_summary()

    def _init_summary(self) -> None:
        _zero_taxes = {tax_field: 0 for tax_field in TAX_FIELDS}

        self.summary = {
            "A": {
                "Inputs": {**_zero_taxes},
                "Capital Goods": {**_zero_taxes},
                "Input Services": {**_zero_taxes},
            },
            "B": {
                "Inputs": {**_zero_taxes},
                "Capital Goods": {**_zero_taxes},
                "Input Services": {**_zero_taxes},
            },
            "C": {
                "Inputs": {**_zero_taxes},
                "Capital Goods": {**_zero_taxes},
                "Input Services": {**_zero_taxes},
            },
            "D": {
                "Inputs": {**_zero_taxes},
                "Capital Goods": {**_zero_taxes},
            },
            "E": {**_zero_taxes},
            "F": {**_zero_taxes},
        }

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

        for row in data:
            self._add_to_summary(row)

        return self._build_transformed_summary()

    def _add_to_summary(self, row: dict) -> None:
        category = self.get_category(row)
        subcategory = self.get_subcategory(category, row)

        if subcategory:
            summary_entry = self.summary[category][subcategory]
        else:
            summary_entry = self.summary[category]

        for tax_field in TAX_FIELDS:
            summary_entry[tax_field] += getattr(row, tax_field)

    def _build_transformed_summary(self) -> list[dict]:
        transformed = []

        for category, summary in self.summary.items():
            title = self.get_title(category)
            has_subcategory = self.has_subcategory(category)

            transformed.append(
                self._create_entry(
                    f"{category}) {title}",
                    self._aggregate_summary(summary) if has_subcategory else summary,
                    indent=0,
                )
            )

            if has_subcategory:
                for subcategory, sub_summary in summary.items():
                    transformed.append(
                        self._create_entry(subcategory, sub_summary, indent=1)
                    )
            else:
                transformed.append(self._create_entry(title, summary, indent=1))

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
