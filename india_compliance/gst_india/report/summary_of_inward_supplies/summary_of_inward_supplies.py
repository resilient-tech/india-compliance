# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import LiteralValue

MAPPING_FIELD = {
    1: {
        "title": "Inward supplies (other than imports and inward supplies liable to reverse charge but includes services received from SEZs)",
        "get_detail_type": lambda row: row.get("gst_category") != "Overseas"
        and row.get("is_reverse_charge") == 0,
    },
    2: {
        "title": "Inward supplies received from unregistered persons liable to reverse charge (other than B above) on which tax is paid & ITC availed",
        "get_detail_type": lambda row: row.get("gst_category") == "Unregistered"
        and row.get("is_reverse_charge") == 1
        and row.get("is_ineligible_for_itc") == 0,
    },
    3: {
        "title": "Inward supplies received from registered persons liable to reverse charge (other than B above) on which tax is paid & ITC availed",
        "get_detail_type": lambda row: row.get("gst_category") != "Unregistered"
        and row.get("is_reverse_charge") == 1
        and row.get("is_ineligible_for_itc") == 0,
    },
    4: {
        "title": "Import Of Goods (including supplies from SEZ)",
        "get_detail_type": lambda row: row.get("itc_classification")
        == "Import Of Goods",
    },
    5: {
        "title": "Import Of Services (excluding inward supplies from SEZ)",
        "get_detail_type": lambda row: row.get("itc_classification")
        == "Import Of Service"
        and row.get("gst_category") != "SEZ",
    },
    6: {
        "title": "Input Tax credit received from ISD",
        "get_detail_type": lambda row: row.get("itc_classification")
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
            "fieldname": "integrated_tax",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "label": _("Central tax (₹)"),
            "fieldname": "central_tax",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "label": _("State/UT tax (₹)"),
            "fieldname": "state_ut_tax",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "label": _("Cess (₹)"),
            "fieldname": "cess",
            "fieldtype": "Currency",
            "width": 150,
        },
    ]


def get_data(filters) -> list[dict]:
    data = []
    data.extend(get_purchase_invoice_data(filters))
    data.extend(get_bill_of_entry_data(filters))

    summary = get_initial_summary()

    for row in data:
        detail_type = get_detail_type(row)
        if detail_type in (1, 2, 3, 4):
            add_subcategory_summary(summary[detail_type], row)

        elif detail_type in (5, 6):
            summary[detail_type]["integrated_tax"] += row.igst_amount
            summary[detail_type]["central_tax"] += row.cgst_amount
            summary[detail_type]["state_ut_tax"] += row.sgst_amount
            summary[detail_type]["cess"] += row.cess_amount

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
    _tax_amount = {
        "integrated_tax": 0,
        "central_tax": 0,
        "state_ut_tax": 0,
        "cess": 0,
    }

    return {
        1: {
            "Inputs": {**_tax_amount},
            "Capital Goods": {**_tax_amount},
            "Input Services": {**_tax_amount},
        },
        2: {
            "Inputs": {**_tax_amount},
            "Capital Goods": {**_tax_amount},
            "Input Services": {**_tax_amount},
        },
        3: {
            "Inputs": {**_tax_amount},
            "Capital Goods": {**_tax_amount},
            "Input Services": {**_tax_amount},
        },
        4: {
            "Inputs": {**_tax_amount},
            "Capital Goods": {**_tax_amount},
        },
        5: {**_tax_amount},
        6: {**_tax_amount},
    }


def get_detail_type(row) -> int:
    for detail_type, mapping in MAPPING_FIELD.items():
        if mapping["get_detail_type"](row):
            return detail_type


def add_subcategory_summary(summary, row) -> dict:
    if row["is_fixed_asset"] == 1:
        key = "Capital Goods"

    elif row["gst_hsn_code"] and row["gst_hsn_code"].startswith("99"):
        key = "Input Services"
    else:
        key = "Inputs"

    summary[key]["integrated_tax"] += row.igst_amount
    summary[key]["central_tax"] += row.cgst_amount
    summary[key]["state_ut_tax"] += row.sgst_amount
    summary[key]["cess"] += row.cess_amount


def get_transformed_summary(summary) -> list[dict]:
    transformed_summary = []
    for detail_type, subcategory in summary.items():
        if detail_type in (1, 2, 3, 4):
            transformed_summary.append(
                {
                    "details": MAPPING_FIELD[detail_type]["title"],
                    "integrated_tax": sum(
                        [
                            subcategory[subcat]["integrated_tax"]
                            for subcat in subcategory
                        ]
                    ),
                    "central_tax": sum(
                        [subcategory[subcat]["central_tax"] for subcat in subcategory]
                    ),
                    "state_ut_tax": sum(
                        [subcategory[subcat]["state_ut_tax"] for subcat in subcategory]
                    ),
                    "cess": sum(
                        [subcategory[subcat]["cess"] for subcat in subcategory]
                    ),
                    "indent": 0,
                }
            )

            for subcategory_name, tax_amounts in subcategory.items():
                transformed_summary.append(
                    {
                        "details": subcategory_name,
                        "integrated_tax": tax_amounts["integrated_tax"],
                        "central_tax": tax_amounts["central_tax"],
                        "state_ut_tax": tax_amounts["state_ut_tax"],
                        "cess": tax_amounts["cess"],
                        "indent": 1,
                    }
                )

        else:
            transformed_summary.append(
                {
                    "details": MAPPING_FIELD[detail_type]["title"],
                    "integrated_tax": subcategory["integrated_tax"],
                    "central_tax": subcategory["central_tax"],
                    "state_ut_tax": subcategory["state_ut_tax"],
                    "cess": subcategory["cess"],
                    "indent": 0,
                }
            )

    return transformed_summary
