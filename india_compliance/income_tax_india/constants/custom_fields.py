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
            "fieldname": "section",
            "insert_after": "round_off_tax_amount",
            "fieldtype": "Select",
            "options": "193\n194\n194BB\n194EE\n194A\n194B\n194C\n194D\n194F\n194G\n194H\n194I\n194JA\n194JB\n194LA\n194I(a)\n194I(b)\n194LBA\n194DA\n192A\n194LBB\n194IA\n194N",
            "sort_options": 1,
        },
        {
            "label": "Entity",
            "fieldname": "entity_type",
            "insert_after": "tax_on_excess_amount",
            "fieldtype": "Select",
            "options": "Individual\nCompany\nCompany Assessee\nNo PAN / Invalid PAN",
        },
    ],
}
