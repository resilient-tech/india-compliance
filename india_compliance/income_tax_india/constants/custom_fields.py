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
    "Salary Component": [
        {
            "fieldname": "component_type",
            "label": "Component Type",
            "fieldtype": "Select",
            "insert_after": "description",
            "options": (
                "\nProvident Fund\nAdditional Provident Fund\nProvident Fund"
                " Loan\nProfessional Tax"
            ),
            "depends_on": 'eval:doc.type == "Deduction"',
            "translatable": 0,
        },
    ],
    "Employee": [
        {
            "fieldname": "ifsc_code",
            "label": "IFSC Code",
            "fieldtype": "Data",
            "insert_after": "bank_ac_no",
            "print_hide": 1,
            "depends_on": 'eval:doc.salary_mode == "Bank"',
            "translatable": 0,
        },
        {
            "fieldname": "pan_number",
            "label": "PAN Number",
            "fieldtype": "Data",
            "insert_after": "payroll_cost_center",
            "print_hide": 1,
            "translatable": 0,
        },
        {
            "fieldname": "micr_code",
            "label": "MICR Code",
            "fieldtype": "Data",
            "insert_after": "ifsc_code",
            "print_hide": 1,
            "depends_on": 'eval:doc.salary_mode == "Bank"',
            "translatable": 0,
        },
        {
            "fieldname": "provident_fund_account",
            "label": "Provident Fund Account",
            "fieldtype": "Data",
            "insert_after": "pan_number",
            "translatable": 0,
        },
    ],
    "Company": [
        {
            "fieldname": "hra_section",
            "label": "HRA Settings",
            "fieldtype": "Section Break",
            "insert_after": "asset_received_but_not_billed",
            "collapsible": 1,
        },
        {
            "fieldname": "basic_component",
            "label": "Basic Component",
            "fieldtype": "Link",
            "options": "Salary Component",
            "insert_after": "hra_section",
        },
        {
            "fieldname": "hra_component",
            "label": "HRA Component",
            "fieldtype": "Link",
            "options": "Salary Component",
            "insert_after": "basic_component",
        },
        {
            "fieldname": "hra_column_break",
            "fieldtype": "Column Break",
            "insert_after": "hra_component",
        },
        {
            "fieldname": "arrear_component",
            "label": "Arrear Component",
            "fieldtype": "Link",
            "options": "Salary Component",
            "insert_after": "hra_column_break",
        },
        {
            "fieldname": "non_profit_section",
            "label": "Non Profit Settings",
            "fieldtype": "Section Break",
            "insert_after": "arrear_component",
            "collapsible": 1,
        },
        {
            "fieldname": "company_80g_number",
            "label": "80G Number",
            "fieldtype": "Data",
            "insert_after": "non_profit_section",
            "translatable": 0,
        },
        {
            "fieldname": "with_effect_from",
            "label": "80G With Effect From",
            "fieldtype": "Date",
            "insert_after": "company_80g_number",
        },
    ]
    + party_fields,
    "Employee Tax Exemption Declaration": [
        {
            "fieldname": "hra_section",
            "label": "HRA Exemption",
            "fieldtype": "Section Break",
            "insert_after": "declarations",
        },
        {
            "fieldname": "monthly_house_rent",
            "label": "Monthly House Rent",
            "fieldtype": "Currency",
            "insert_after": "hra_section",
        },
        {
            "fieldname": "rented_in_metro_city",
            "label": "Rented in Metro City",
            "fieldtype": "Check",
            "insert_after": "monthly_house_rent",
            "depends_on": "monthly_house_rent",
        },
        {
            "fieldname": "salary_structure_hra",
            "label": "HRA as per Salary Structure",
            "fieldtype": "Currency",
            "insert_after": "rented_in_metro_city",
            "read_only": 1,
            "depends_on": "monthly_house_rent",
        },
        {
            "fieldname": "hra_column_break",
            "fieldtype": "Column Break",
            "insert_after": "salary_structure_hra",
            "depends_on": "monthly_house_rent",
        },
        {
            "fieldname": "annual_hra_exemption",
            "label": "Annual HRA Exemption",
            "fieldtype": "Currency",
            "insert_after": "hra_column_break",
            "read_only": 1,
            "depends_on": "monthly_house_rent",
        },
        {
            "fieldname": "monthly_hra_exemption",
            "label": "Monthly HRA Exemption",
            "fieldtype": "Currency",
            "insert_after": "annual_hra_exemption",
            "read_only": 1,
            "depends_on": "monthly_house_rent",
        },
    ],
    "Employee Tax Exemption Proof Submission": [
        {
            "fieldname": "hra_section",
            "label": "HRA Exemption",
            "fieldtype": "Section Break",
            "insert_after": "tax_exemption_proofs",
        },
        {
            "fieldname": "house_rent_payment_amount",
            "label": "House Rent Payment Amount",
            "fieldtype": "Currency",
            "insert_after": "hra_section",
        },
        {
            "fieldname": "rented_in_metro_city",
            "label": "Rented in Metro City",
            "fieldtype": "Check",
            "insert_after": "house_rent_payment_amount",
            "depends_on": "house_rent_payment_amount",
        },
        {
            "fieldname": "rented_from_date",
            "label": "Rented From Date",
            "fieldtype": "Date",
            "insert_after": "rented_in_metro_city",
            "depends_on": "house_rent_payment_amount",
        },
        {
            "fieldname": "rented_to_date",
            "label": "Rented To Date",
            "fieldtype": "Date",
            "insert_after": "rented_from_date",
            "depends_on": "house_rent_payment_amount",
        },
        {
            "fieldname": "hra_column_break",
            "fieldtype": "Column Break",
            "insert_after": "rented_to_date",
            "depends_on": "house_rent_payment_amount",
        },
        {
            "fieldname": "monthly_house_rent",
            "label": "Monthly House Rent",
            "fieldtype": "Currency",
            "insert_after": "hra_column_break",
            "read_only": 1,
            "depends_on": "house_rent_payment_amount",
        },
        {
            "fieldname": "monthly_hra_exemption",
            "label": "Monthly Eligible Amount",
            "fieldtype": "Currency",
            "insert_after": "monthly_house_rent",
            "read_only": 1,
            "depends_on": "house_rent_payment_amount",
        },
        {
            "fieldname": "total_eligible_hra_exemption",
            "label": "Total Eligible HRA Exemption",
            "fieldtype": "Currency",
            "insert_after": "monthly_hra_exemption",
            "read_only": 1,
            "depends_on": "house_rent_payment_amount",
        },
    ],
    "Supplier": party_fields,
    "Customer": party_fields,
    "Finance Book": [
        {
            "fieldname": "for_income_tax",
            "label": "For Income Tax",
            "fieldtype": "Check",
            "insert_after": "finance_book_name",
            "description": (
                "If the asset is put to use for less than 180 days, the first"
                " Depreciation Rate will be reduced by 50%."
            ),
        }
    ],
}
