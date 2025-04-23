# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import LiteralValue

MAPPING_FIELD = {
    1: {
        "title": "Inward supplies (other than imports and inward supplies liable to reverse charge but includes services received from SEZs)",
        "is_part_of": lambda row: row.get("gst_category") != "Overseas"
        and row.get("is_reverse_charge") == 0,
    },
    2: {
        "title": "Inward supplies received from unregistered persons liable to reverse charge (other than B above) on which tax is paid & ITC availed",
        "is_part_of": lambda row: row.get("gst_category") == "Unregistered"
        and row.get("is_reverse_charge") == 1
        and row.get("is_ineligible_for_itc") == 0,
    },
    3: {
        "title": "Inward supplies received from registered persons liable to reverse charge (other than B above) on which tax is paid & ITC availed",
        "is_part_of": lambda row: row.get("gst_category") != "Unregistered"
        and row.get("is_reverse_charge") == 1
        and row.get("is_ineligible_for_itc") == 0,
    },
    4: {
        "title": "Import Of Goods (including supplies from SEZ)",
        "is_part_of": lambda row: row.get("itc_classification") == "Import Of Goods"
        and row.get("gst_category") == "SEZ",
    },
    5: {
        "title": "Import Of Services (excluding inward supplies from SEZ)",
        "is_part_of": lambda row: row.get("itc_classification") == "Import Of Service"
        and row.get("gst_category") != "SEZ",
    },
    6: {
        "title": "Input Tax credit received from ISD",
        "is_part_of": lambda row: row.get("itc_classification")
        == "Input Service Distributor",
    },
}


def execute(filters: dict | None = None) -> tuple[list[dict], list[dict]]:
    return get_columns(), get_data(filters)


def get_columns() -> list[dict]:
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


def get_data(filters: dict) -> list[dict]:
    data = []
    data.extend(get_purchase_invoice_data(filters))
    data.extend(get_bill_of_entry_data(filters))

    summary = get_initial_summary()

    for row in data:
        detail_type = get_detail_type(row)
        if detail_type in (1, 2, 3, 4):
            add_subcategory_summary(summary[detail_type], row)

        elif detail_type in (5, 6):
            summary[detail_type]["igst_amount"] += row.igst_amount
            summary[detail_type]["cgst_amount"] += row.cgst_amount
            summary[detail_type]["sgst_amount"] += row.sgst_amount
            summary[detail_type]["cess_amount"] += row.cess_amount

    return get_transformed_summary(summary)


def get_purchase_invoice_data(filters: dict) -> list[list]:
    doc = frappe.qb.DocType("Purchase Invoice")
    doc_item = frappe.qb.DocType("Purchase Invoice Item")

    from_date, to_date = filters.date_range

    query = (
        frappe.qb.from_(doc)
        .inner_join(doc_item)
        .on(doc.name == doc_item.parent)
        .select(
            doc.gst_category.as_("gst_category"),
            doc.itc_classification.as_("itc_classification"),
            doc_item.is_ineligible_for_itc.as_("is_ineligible_for_itc"),
            doc_item.is_fixed_asset.as_("is_fixed_asset"),
            doc.is_reverse_charge.as_("is_reverse_charge"),
            doc_item.gst_hsn_code.as_("gst_hsn_code"),
            doc_item.cgst_amount.as_("cgst_amount"),
            doc_item.sgst_amount.as_("sgst_amount"),
            doc_item.igst_amount.as_("igst_amount"),
            (doc_item.cess_amount + doc_item.cess_non_advol_amount).as_("cess_amount"),
        )
        .where(
            (doc.docstatus == 1)
            & (doc.posting_date[from_date:to_date])
            & (doc.company == filters.company)
            & (doc.is_opening == "No")
        )
    )

    if filters.get("company_gstin"):
        query = query.where(doc.company_gstin == filters.company_gstin)

    return query.run(as_dict=True)


def get_bill_of_entry_data(filters: dict) -> list[list]:
    doc = frappe.qb.DocType("Bill of Entry")
    item = frappe.qb.DocType("Item")
    doc_item = frappe.qb.DocType("Bill of Entry Item")

    from_date, to_date = filters.date_range

    query = (
        frappe.qb.from_(doc)
        .inner_join(doc_item)
        .on(doc.name == doc_item.parent)
        .inner_join(item)
        .on(doc_item.item_code == item.name)
        .select(
            Case("itc_classification")
            .when(doc_item.gst_hsn_code.like("99%"), "Import Of Service")
            .else_("Import Of Goods"),
            LiteralValue("'Overseas'").as_("gst_category"),
            LiteralValue(False).as_("is_reverse_charge"),
            item.is_fixed_asset.as_("is_fixed_asset"),
            doc_item.gst_hsn_code.as_("gst_hsn_code"),
            doc_item.cgst_amount.as_("cgst_amount"),
            doc_item.sgst_amount.as_("sgst_amount"),
            doc_item.igst_amount.as_("igst_amount"),
            (doc_item.cess_amount + doc_item.cess_non_advol_amount).as_("cess_amount"),
        )
        .where(
            (doc.docstatus == 1)
            & (doc.posting_date[from_date:to_date])
            & (doc.company == filters.company)
        )
    )

    return query.run(as_dict=True)


def get_initial_summary() -> dict:
    zero_taxes = {
        "igst_amount": 0,
        "cgst_amount": 0,
        "sgst_amount": 0,
        "cess_amount": 0,
    }

    return {
        1: {
            "Inputs": {**zero_taxes},
            "Capital Goods": {**zero_taxes},
            "Input Services": {**zero_taxes},
        },
        2: {
            "Inputs": {**zero_taxes},
            "Capital Goods": {**zero_taxes},
            "Input Services": {**zero_taxes},
        },
        3: {
            "Inputs": {**zero_taxes},
            "Capital Goods": {**zero_taxes},
            "Input Services": {**zero_taxes},
        },
        4: {
            "Inputs": {**zero_taxes},
            "Capital Goods": {**zero_taxes},
        },
        5: {**zero_taxes},
        6: {**zero_taxes},
    }


def get_detail_type(row: dict) -> int:
    for detail_type, mapping in MAPPING_FIELD.items():
        if mapping["is_part_of"](row):
            return detail_type


def add_subcategory_summary(summary: dict, row: dict) -> None:
    if row["is_fixed_asset"] == 1:
        key = "Capital Goods"

    elif row["gst_hsn_code"] and row["gst_hsn_code"].startswith("99"):
        key = "Input Services"

    else:
        key = "Inputs"

    summary[key]["igst_amount"] += row.igst_amount
    summary[key]["cgst_amount"] += row.cgst_amount
    summary[key]["sgst_amount"] += row.sgst_amount
    summary[key]["cess_amount"] += row.cess_amount


def get_transformed_summary(summary: dict) -> list[dict]:
    transformed_summary = []

    for detail_type, subcategory in summary.items():
        title = MAPPING_FIELD[detail_type]["title"]

        if detail_type in (1, 2, 3, 4):
            # Add aggregated row
            total_taxes = aggregate_taxes(subcategory)
            transformed_summary.append(
                get_tax_summary_row(title, total_taxes, indent=0)
            )

            # Add individual subcategory rows
            for subcat_name, taxes in subcategory.items():
                transformed_summary.append(
                    get_tax_summary_row(subcat_name, taxes, indent=1)
                )
        else:
            # Add single row
            transformed_summary.append(
                get_tax_summary_row(title, subcategory, indent=0)
            )

    return transformed_summary


def get_tax_summary_row(details: str, taxes: dict, indent: int = 0) -> dict:
    return {
        "details": details,
        "igst_amount": taxes.get("igst_amount", 0),
        "cgst_amount": taxes.get("cgst_amount", 0),
        "sgst_amount": taxes.get("sgst_amount", 0),
        "cess_amount": taxes.get("cess_amount", 0),
        "indent": indent,
    }


def aggregate_taxes(subcategory: dict) -> dict:
    return {
        "igst_amount": sum(
            tax_item.get("igst_amount", 0) for tax_item in subcategory.values()
        ),
        "cgst_amount": sum(
            tax_item.get("cgst_amount", 0) for tax_item in subcategory.values()
        ),
        "sgst_amount": sum(
            tax_item.get("sgst_amount", 0) for tax_item in subcategory.values()
        ),
        "cess_amount": sum(
            tax_item.get("cess_amount", 0) for tax_item in subcategory.values()
        ),
    }
