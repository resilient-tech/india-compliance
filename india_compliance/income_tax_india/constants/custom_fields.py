import frappe

from india_compliance.income_tax_india.constants import (
    NEW_TDS_SECTIONS,
    OLD_TDS_SECTIONS,
    TDS_ENTITY_TYPE,
    get_tds_section_value,
)

old_tds_section_options = "\n" + "\n".join(sorted(OLD_TDS_SECTIONS))
tds_entity_type_options = "\n" + "\n".join(sorted(TDS_ENTITY_TYPE))

tds_section_options = frappe.as_json(
    [
        {
            "label": get_tds_section_value(section),
            "value": get_tds_section_value(section),
            "description": section.get("description", ""),
        }
        for section in NEW_TDS_SECTIONS
    ]
)

party_fields = [
    {
        "fieldname": "pan",
        "label": "PAN",
        "fieldtype": "Data",
        "insert_after": "gstin",
        "read_only_depends_on": "eval: doc.gstin",
        "translatable": 0,
    },
]


# MSME
supplier_msme_fields = [
    {
        "fieldname": "msme_registration",
        "label": "MSME Registration",
        "fieldtype": "Link",
        "options": "MSME Registration",
        "insert_after": "is_reverse_charge_applicable",
    },
]


purchase_invoice_msme_fields = [
    {
        "fieldname": "msme_registration",
        "label": "MSME Registration",
        "fieldtype": "Autocomplete",
        "insert_after": "gst_category",
        "fetch_from": "",
        "print_hide": 1,
        "translatable": 0,
    },
]


CUSTOM_FIELDS = {
    "Company": party_fields,
    "Customer": party_fields,
    "Supplier": party_fields + supplier_msme_fields,
    "Purchase Invoice": purchase_invoice_msme_fields,
    "Finance Book": [
        {
            "fieldname": "for_income_tax",
            "label": "For Income Tax",
            "fieldtype": "Check",
            "insert_after": "finance_book_name",
            "description": (
                "If the asset is put to use for less than 180 days in the first year, the first year's"
                " Depreciation Rate will be reduced by 50%."
            ),
        }
    ],
    "Tax Withholding Category": [
        {
            "label": "Income Tax Details",
            "fieldname": "income_tax_details_section",
            "insert_after": "disable_transaction_threshold",
            "fieldtype": "Section Break",
        },
        {
            "label": "Section",
            "fieldname": "tds_section",
            "insert_after": "income_tax_details_section",
            "fieldtype": "Autocomplete",
            "options": tds_section_options,
            "translatable": 0,
            "mandatory_depends_on": "eval:doc.entity_type",
        },
        {
            "label": "Old Income Tax Section",
            "fieldname": "old_income_tax_section",
            "insert_after": "tds_section",
            "fieldtype": "Autocomplete",
            "options": old_tds_section_options,
            "read_only": 1,
            "translatable": 0,
            "description": "Section under Income Tax Act-1961 (pre FY 2026-27)",
        },
        {
            "fieldname": "income_tax_details_column_break",
            "insert_after": "old_income_tax_section",
            "fieldtype": "Column Break",
        },
        {
            "label": "Entity",
            "fieldname": "entity_type",
            "insert_after": "income_tax_details_column_break",
            "fieldtype": "Select",
            "options": tds_entity_type_options,
            "translatable": 0,
            "mandatory_depends_on": "eval:doc.tds_section",
        },
    ],
}
