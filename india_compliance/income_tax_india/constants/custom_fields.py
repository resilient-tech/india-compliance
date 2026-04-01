from india_compliance.income_tax_india.constants import (
    NEW_TDS_SECTIONS,
    OLD_TDS_SECTIONS,
    TDS_ENTITY_TYPE,
)

tds_section_options = "\n" + "\n".join(sorted(NEW_TDS_SECTIONS))
old_tds_section_options = "\n" + "\n".join(sorted(OLD_TDS_SECTIONS))
tds_entity_type_options = "\n" + "\n".join(sorted(TDS_ENTITY_TYPE))

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

CUSTOM_FIELDS = {
    "Company": party_fields,
    "Customer": party_fields,
    "Supplier": party_fields,
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
            "label": "Section",
            "fieldname": "tds_section",
            "insert_after": "round_off_tax_amount",
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
            "label": "Entity",
            "fieldname": "entity_type",
            "insert_after": "tax_on_excess_amount",
            "fieldtype": "Select",
            "options": tds_entity_type_options,
            "translatable": 0,
            "mandatory_depends_on": "eval:doc.tds_section",
        },
    ],
}
