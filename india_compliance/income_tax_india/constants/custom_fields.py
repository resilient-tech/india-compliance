from india_compliance.income_tax_india.constants import OLD_TDS_SECTIONS, TDS_ENTITY_TYPE

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


# MSME
supplier_msme_fields = [
    {
        "fieldname": "msme_section",
        "label": "MSME Details",
        "fieldtype": "Section Break",
        "insert_after": "pan",
        "collapsible": 1,
    },
    {
        "fieldname": "msme_registration",
        "label": "MSME Registration",
        "fieldtype": "Link",
        "options": "MSME",
        "insert_after": "msme_section",
        "description": "UDYAM registration of the supplier.",
    },
    {
        "fieldname": "msme_enterprise_type",
        "label": "Enterprise Type",
        "fieldtype": "Data",
        "insert_after": "msme_registration",
        "depends_on": "eval:doc.msme_registration",
        "is_virtual": 1,
        "read_only": 1,
        "translatable": 0,
    },
    {
        "fieldname": "msme_column_break",
        "fieldtype": "Column Break",
        "insert_after": "msme_enterprise_type",
    },
    {
        "fieldname": "msme_activity",
        "label": "Activity",
        "fieldtype": "Data",
        "insert_after": "msme_column_break",
        "depends_on": "eval:doc.msme_registration",
        "is_virtual": 1,
        "read_only": 1,
        "translatable": 0,
    },
    {
        "fieldname": "msme_is_cancelled",
        "label": "Registration Cancelled",
        "fieldtype": "Check",
        "insert_after": "msme_activity",
        "hidden": 1,
        "is_virtual": 1,
        "read_only": 1,
    },
]


purchase_invoice_msme_fields = [
    {
        "fieldname": "msme_registration",
        "label": "MSME Registration",
        "fieldtype": "Link",
        "options": "MSME",
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
            "label": "Section",
            "fieldname": "tds_section",
            "insert_after": "round_off_tax_amount",
            "fieldtype": "Autocomplete",
            "options": None,
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
