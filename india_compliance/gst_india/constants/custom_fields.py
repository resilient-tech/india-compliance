import frappe

from india_compliance.gst_india.constants import GST_CATEGORIES, STATE_NUMBERS

state_options = "\n" + "\n".join(STATE_NUMBERS)
gst_category_options = "\n".join(GST_CATEGORIES)
default_gst_category = "Unregistered"


def get_place_of_supply_options():
    options = []

    for state_name, state_number in STATE_NUMBERS.items():
        options.append(f"{state_number}-{state_name}")

    options.append("96-Other Countries")
    return "\n".join(sorted(options))


party_fields = [
    {
        "fieldname": "tax_details_section",
        "label": "Tax Details",
        "fieldtype": "Section Break",
        "insert_after": "tax_withholding_category",
    },
    {
        "fieldname": "gstin",
        "label": "GSTIN / UIN",
        "fieldtype": "Autocomplete",
        "insert_after": "tax_details_section",
        "translatable": 0,
    },
    {
        "fieldname": "tax_details_column_break",
        "fieldtype": "Column Break",
        "insert_after": "pan",
    },
    {
        "fieldname": "gst_category",
        "label": "GST Category",
        "fieldtype": "Select",
        "insert_after": "tax_details_column_break",
        "options": gst_category_options,
        "default": default_gst_category,
        "reqd": 1,
        "translatable": 0,
    },
]

CUSTOM_FIELDS = {
    "Company": [
        {
            **party_fields[0],
            "insert_after": "parent_company",
        },
        *party_fields[1:],
        {
            "fieldname": "default_customs_expense_account",
            "label": "Default Customs Duty Expense Account",
            "fieldtype": "Link",
            "options": "Account",
            "insert_after": "unrealized_profit_loss_account",
        },
        {
            "fieldname": "default_customs_payable_account",
            "label": "Default Customs Duty Payable Account",
            "fieldtype": "Link",
            "options": "Account",
            "insert_after": "default_finance_book",
        },
    ],
    ("Customer", "Supplier"): party_fields,
    # Purchase Fields
    ("Purchase Order", "Purchase Receipt", "Purchase Invoice"): [
        {
            "fieldname": "supplier_gstin",
            "label": "Supplier GSTIN",
            "fieldtype": "Data",
            "insert_after": "address_display",
            "fetch_from": "supplier_address.gstin",
            "print_hide": 1,
            "read_only": 1,
            "translatable": 0,
        },
        {
            "fieldname": "gst_category",
            "label": "GST Category",
            "fieldtype": "Data",
            "insert_after": "supplier_gstin",
            "read_only": 1,
            "print_hide": 1,
            # values set to None to remove them from earlier installations
            "options": None,
            "default": None,
            "fetch_from": "supplier_address.gst_category",
            "translatable": 0,
        },
        {
            "fieldname": "company_gstin",
            "label": "Company GSTIN",
            "fieldtype": "Data",
            "insert_after": "billing_address_display",
            "fetch_from": "billing_address.gstin",
            "print_hide": 1,
            "read_only": 1,
            "translatable": 0,
        },
        {
            "fieldname": "place_of_supply",
            "label": "Place of Supply",
            "fieldtype": "Autocomplete",
            "options": get_place_of_supply_options(),
            "insert_after": "company_gstin",
            "print_hide": 1,
            "read_only": 0,
            "translatable": 0,
        },
        {
            "fieldname": "is_reverse_charge",
            "label": "Is Reverse Charge",
            "fieldtype": "Check",
            "insert_after": "apply_tds",
            "print_hide": 1,
            "default": 0,
        },
    ],
    # Sales - Export with GST Payment
    # POS Invoice excluded, since it isn't designed for exports
    ("Quotation", "Sales Order", "Delivery Note", "Sales Invoice"): {
        "fieldname": "is_export_with_gst",
        "label": "Is Export With Payment of GST",
        "fieldtype": "Check",
        "insert_after": "is_reverse_charge",
        "print_hide": 1,
        "depends_on": 'eval:in_list(["SEZ", "Overseas"], doc.gst_category)',
        "default": 0,
        "translatable": 0,
    },
    # Sales - GST Details Section
    ("Sales Order", "Delivery Note", "Sales Invoice"): [
        {
            "fieldname": "gst_section",
            "label": "GST Details",
            "fieldtype": "Section Break",
            "insert_after": "gst_vehicle_type",
            "print_hide": 1,
            "collapsible": 1,
        },
        {
            "fieldname": "ecommerce_gstin",
            "label": "E-commerce GSTIN",
            "length": 15,
            "fieldtype": "Data",
            "insert_after": "gst_section",
            "print_hide": 1,
            "translatable": 0,
        },
        {
            "fieldname": "gst_col_break",
            "fieldtype": "Column Break",
            "insert_after": "ecommerce_gstin",
        },
    ],
    # Sales GSTIN Fields
    ("Quotation", "Sales Order", "Delivery Note", "Sales Invoice", "POS Invoice"): [
        {
            "fieldname": "billing_address_gstin",
            "label": "Billing Address GSTIN",
            "fieldtype": "Data",
            "insert_after": "address_display",
            "read_only": 1,
            "fetch_from": "customer_address.gstin",
            "print_hide": 1,
            "length": 15,
            "translatable": 0,
        },
        {
            "fieldname": "gst_category",
            "label": "GST Category",
            "fieldtype": "Data",
            "insert_after": "billing_address_gstin",
            "read_only": 1,
            "print_hide": 1,
            # values set to None to remove them from earlier installations
            "options": None,
            "default": None,
            "fetch_from": "customer_address.gst_category",
            "translatable": 0,
        },
        {
            "fieldname": "place_of_supply",
            "label": "Place of Supply",
            "fieldtype": "Autocomplete",
            "options": get_place_of_supply_options(),
            "insert_after": "gst_category",
            "print_hide": 1,
            "read_only": 0,
            "length": 50,
            "translatable": 0,
        },
        {
            "fieldname": "company_gstin",
            "label": "Company GSTIN",
            "fieldtype": "Data",
            "insert_after": "company_address",
            "fetch_from": "company_address.gstin",
            "print_hide": 1,
            "read_only": 1,
            "length": 15,
            "translatable": 0,
        },
    ],
    # Sales Shipping Fields
    ("Delivery Note", "Sales Invoice"): [
        {
            "fieldname": "port_code",
            "label": "Port Code",
            "fieldtype": "Data",
            "insert_after": "gst_col_break",
            "print_hide": 1,
            "depends_on": "eval:doc.gst_category == 'Overseas' ",
            "length": 15,
            "translatable": 0,
        },
        {
            "fieldname": "shipping_bill_number",
            "label": " Shipping Bill Number",
            "fieldtype": "Data",
            "insert_after": "port_code",
            "print_hide": 1,
            "depends_on": "eval:doc.gst_category == 'Overseas' ",
            "length": 50,
            "translatable": 0,
        },
        {
            "fieldname": "shipping_bill_date",
            "label": "Shipping Bill Date",
            "fieldtype": "Date",
            "insert_after": "shipping_bill_number",
            "print_hide": 1,
            "depends_on": "eval:doc.gst_category == 'Overseas' ",
        },
    ],
    # Transaction Item Fields
    (
        "Material Request Item",
        "Supplier Quotation Item",
        "Purchase Order Item",
        "Purchase Receipt Item",
        "Purchase Invoice Item",
        "Quotation Item",
        "Sales Order Item",
        "Delivery Note Item",
        "Sales Invoice Item",
        "POS Invoice Item",
    ): [
        {
            "fieldname": "gst_hsn_code",
            "label": "HSN/SAC",
            "fieldtype": "Data",
            "fetch_from": "item_code.gst_hsn_code",
            "insert_after": "description",
            "allow_on_submit": 1,
            "print_hide": 1,
            "fetch_if_empty": 1,
            "translatable": 0,
        },
        {
            "fieldname": "is_nil_exempt",
            "label": "Is Nil Rated or Exempted",
            "fieldtype": "Check",
            "fetch_from": "item_code.is_nil_exempt",
            "insert_after": "gst_hsn_code",
            "print_hide": 1,
        },
        {
            "fieldname": "is_non_gst",
            "label": "Is Non GST",
            "fieldtype": "Check",
            "fetch_from": "item_code.is_non_gst",
            "insert_after": "is_nil_exempt",
            "print_hide": 1,
        },
    ],
    # Taxable Value
    (
        "Delivery Note Item",
        "Sales Invoice Item",
        "POS Invoice Item",
        "Purchase Invoice Item",
    ): [
        {
            "fieldname": "taxable_value",
            "label": "Taxable Value",
            "fieldtype": "Currency",
            "insert_after": "base_net_amount",
            "hidden": 1,
            "options": "Company:company:default_currency",
            "print_hide": 1,
        },
    ],
    "Sales Invoice": [
        {
            "fieldname": "invoice_copy",
            "label": "Invoice Copy",
            "length": 30,
            "fieldtype": "Select",
            "insert_after": "column_break_84",
            "print_hide": 1,
            "allow_on_submit": 1,
            "options": (
                "Original for Recipient\nDuplicate for Transporter\nDuplicate for"
                " Supplier\nTriplicate for Supplier"
            ),
            "translatable": 0,
        },
        {
            "fieldname": "reason_for_issuing_document",
            "label": "Reason For Issuing Document",
            "fieldtype": "Select",
            "insert_after": "return_against",
            "print_hide": 1,
            "depends_on": "eval:doc.is_return == 1",
            "length": 45,
            "options": (
                "\n01-Sales Return\n02-Post Sale Discount\n03-Deficiency in"
                " services\n04-Correction in Invoice\n05-Change in POS\n06-Finalization"
                " of Provisional assessment\n07-Others"
            ),
            "translatable": 0,
        },
    ],
    "Purchase Invoice": [
        {
            "fieldname": "gst_section",
            "label": "GST Details",
            "fieldtype": "Section Break",
            "insert_after": "language",
            "print_hide": 1,
            "collapsible": 1,
        },
        {
            "fieldname": "eligibility_for_itc",
            "label": "Eligibility For ITC",
            "fieldtype": "Select",
            "insert_after": "gst_section",
            "print_hide": 1,
            "options": (
                "Input Service Distributor\nImport Of Service\nImport Of Capital"
                " Goods\nITC on Reverse Charge\nIneligible As Per Section"
                " 17(5)\nIneligible Others\nAll Other ITC"
            ),
            "default": "All Other ITC",
            "translatable": 0,
        },
        {
            "fieldname": "gst_col_break",
            "fieldtype": "Column Break",
            "insert_after": "eligibility_for_itc",
        },
        {
            "fieldname": "itc_integrated_tax",
            "label": "Availed ITC Integrated Tax",
            "fieldtype": "Currency",
            "insert_after": "gst_col_break",
            "options": "Company:company:default_currency",
            "print_hide": 1,
        },
        {
            "fieldname": "itc_central_tax",
            "label": "Availed ITC Central Tax",
            "fieldtype": "Currency",
            "insert_after": "itc_integrated_tax",
            "options": "Company:company:default_currency",
            "print_hide": 1,
        },
        {
            "fieldname": "itc_state_tax",
            "label": "Availed ITC State/UT Tax",
            "fieldtype": "Currency",
            "insert_after": "itc_central_tax",
            "options": "Company:company:default_currency",
            "print_hide": 1,
        },
        {
            "fieldname": "itc_cess_amount",
            "label": "Availed ITC Cess",
            "fieldtype": "Currency",
            "insert_after": "itc_state_tax",
            "options": "Company:company:default_currency",
            "print_hide": 1,
        },
    ],
    "Supplier": [
        {
            "fieldname": "gst_transporter_id",
            "label": "GST Transporter ID",
            "fieldtype": "Data",
            "insert_after": "gst_category",
            "depends_on": "eval:doc.is_transporter",
            "read_only_depends_on": "eval:doc.gstin",
            "translatable": 0,
        }
    ],
    "Address": [
        {
            "fieldname": "tax_details_section",
            "label": "Tax Details",
            "fieldtype": "Section Break",
            "insert_after": "disabled",
        },
        {
            "fieldname": "gstin",
            "label": "GSTIN / UIN",
            "fieldtype": "Data",
            "insert_after": "tax_details_section",
            "translatable": 0,
        },
        {
            "fieldname": "gst_state",
            "label": "GST State",
            "fieldtype": "Select",
            "options": state_options,
            "insert_after": "gstin",
            "read_only": 1,
            "translatable": 0,
        },
        {
            "fieldname": "tax_details_column_break",
            "fieldtype": "Column Break",
            "insert_after": "gst_state",
        },
        {
            "fieldname": "gst_category",
            "label": "GST Category",
            "fieldtype": "Select",
            "insert_after": "tax_details_column_break",
            "options": gst_category_options,
            "default": default_gst_category,
            "reqd": 1,
            "translatable": 0,
        },
        {
            "fieldname": "gst_state_number",
            "label": "GST State Number",
            "fieldtype": "Data",
            "insert_after": "gst_category",
            "read_only": 1,
            "translatable": 0,
        },
    ],
    "Payment Entry": [
        {
            "fieldname": "gst_section",
            "label": "GST Details",
            "fieldtype": "Section Break",
            "insert_after": "deductions",
            "print_hide": 1,
            "collapsible": 1,
        },
        {
            "fieldname": "company_address",
            "label": "Company Address",
            "fieldtype": "Link",
            "insert_after": "gst_section",
            "print_hide": 1,
            "options": "Address",
        },
        {
            "fieldname": "company_gstin",
            "label": "Company GSTIN",
            "fieldtype": "Data",
            "insert_after": "company_address",
            "fetch_from": "company_address.gstin",
            "print_hide": 1,
            "read_only": 1,
            "translatable": 0,
        },
        {
            "fieldname": "place_of_supply",
            "label": "Place of Supply",
            "fieldtype": "Data",
            "insert_after": "company_gstin",
            "print_hide": 1,
            "read_only": 1,
            "translatable": 0,
        },
        {
            "fieldname": "gst_column_break",
            "fieldtype": "Column Break",
            "insert_after": "place_of_supply",
        },
        {
            "fieldname": "customer_address",
            "label": "Customer Address",
            "fieldtype": "Link",
            "insert_after": "gst_column_break",
            "print_hide": 1,
            "options": "Address",
            "depends_on": 'eval:doc.party_type == "Customer"',
        },
        {
            "fieldname": "customer_gstin",
            "label": "Customer GSTIN",
            "fieldtype": "Data",
            "insert_after": "customer_address",
            "fetch_from": "customer_address.gstin",
            "print_hide": 1,
            "read_only": 1,
            "translatable": 0,
        },
    ],
    "Journal Entry": [
        {
            "fieldname": "reversal_type",
            "label": "Reversal Type",
            "fieldtype": "Select",
            "insert_after": "voucher_type",
            "print_hide": 1,
            "options": "As per rules 42 & 43 of CGST Rules\nOthers",
            "depends_on": "eval:doc.voucher_type == 'Reversal Of ITC'",
            "mandatory_depends_on": "eval:doc.voucher_type == 'Reversal Of ITC'",
            "translatable": 0,
        },
        {
            "fieldname": "company_address",
            "label": "Company Address",
            "fieldtype": "Link",
            "options": "Address",
            "insert_after": "reversal_type",
            "print_hide": 1,
            "depends_on": "eval:doc.voucher_type == 'Reversal Of ITC'",
            "mandatory_depends_on": "eval:doc.voucher_type == 'Reversal Of ITC'",
        },
        {
            "fieldname": "company_gstin",
            "label": "Company GSTIN",
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "company_address",
            "print_hide": 1,
            "fetch_from": "company_address.gstin",
            "depends_on": "eval:doc.voucher_type == 'Reversal Of ITC'",
            "mandatory_depends_on": "eval:doc.voucher_type=='Reversal Of ITC'",
            "translatable": 0,
        },
    ],
    "Tax Category": [
        {
            "fieldname": "is_inter_state",
            "label": "Is Inter State",
            "fieldtype": "Check",
            "insert_after": "disabled",
            "print_hide": 1,
        },
        {
            "fieldname": "is_reverse_charge",
            "label": "Is Reverse Charge",
            "fieldtype": "Check",
            "insert_after": "is_inter_state",
            "print_hide": 1,
        },
        {
            "fieldname": "tax_category_column_break",
            "fieldtype": "Column Break",
            "insert_after": "is_reverse_charge",
        },
        {
            "fieldname": "gst_state",
            "label": "Source State",
            "fieldtype": "Select",
            "options": state_options,
            "insert_after": "company",
            "translatable": 0,
        },
    ],
    "Item": [
        {
            "fieldname": "gst_hsn_code",
            "label": "HSN/SAC",
            "fieldtype": "Link",
            "options": "GST HSN Code",
            "insert_after": "item_group",
            "allow_in_quick_entry": 1,
        },
        {
            "fieldname": "is_nil_exempt",
            "label": "Is Nil Rated or Exempted",
            "fieldtype": "Check",
            "insert_after": "gst_hsn_code",
        },
        {
            "fieldname": "is_non_gst",
            "label": "Is Non GST ",
            "fieldtype": "Check",
            "insert_after": "is_nil_exempt",
        },
    ],
}

reverse_charge_field = frappe._dict(
    fieldname="is_reverse_charge",
    label="Is Reverse Charge",
    fieldtype="Check",
    print_hide=1,
    default=0,
)

# POS Invoice excluded, since it isn't designed for reverse charge transactions
SALES_REVERSE_CHARGE_FIELDS = {
    "Quotation": reverse_charge_field.copy().update(insert_after="customer_name"),
    "Sales Order": reverse_charge_field.copy().update(
        insert_after="skip_delivery_note"
    ),
    "Delivery Note": reverse_charge_field.copy().update(
        insert_after="set_posting_time"
    ),
    "Sales Invoice": reverse_charge_field.copy().update(insert_after="is_debit_note"),
}

E_INVOICE_FIELDS = {
    "Sales Invoice": [
        {
            "fieldname": "irn",
            "label": "IRN",
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "customer",
            "no_copy": 1,
            "print_hide": 1,
            "depends_on": 'eval:doc.gst_category != "Unregistered"',
            "translatable": 0,
        },
        {
            "fieldname": "einvoice_status",
            "label": "e-Invoice Status",
            "fieldtype": "Select",
            "insert_after": "status",
            "options": "\nPending\nGenerated\nCancelled\nFailed",
            "default": None,
            "hidden": 1,
            "no_copy": 1,
            "print_hide": 1,
            "read_only": 1,
            "translatable": 0,
        },
    ]
}

E_WAYBILL_DN_FIELDS = [
    {
        "fieldname": "distance",
        "label": "Distance (in km)",
        "fieldtype": "Int",
        "insert_after": "vehicle_no",
        "print_hide": 1,
        "description": (
            "Set as zero to update distance as per the e-Waybill portal (if available)"
        ),
    },
    {
        "fieldname": "gst_transporter_id",
        "label": "GST Transporter ID",
        "fieldtype": "Data",
        "insert_after": "transporter",
        "fetch_from": "transporter.gst_transporter_id",
        "print_hide": 1,
        "translatable": 0,
    },
    {
        "fieldname": "mode_of_transport",
        "label": "Mode of Transport",
        "fieldtype": "Select",
        "options": "\nRoad\nAir\nRail\nShip",
        "default": "Road",
        "insert_after": "transporter_name",
        "print_hide": 1,
        "translatable": 0,
    },
    {
        "fieldname": "gst_vehicle_type",
        "label": "GST Vehicle Type",
        "fieldtype": "Select",
        "options": "Regular\nOver Dimensional Cargo (ODC)",
        "depends_on": 'eval:["Road", "Ship"].includes(doc.mode_of_transport)',
        "read_only_depends_on": "eval: doc.mode_of_transport == 'Ship'",
        "default": "Regular",
        "insert_after": "lr_date",
        "print_hide": 1,
        "translatable": 0,
    },
    {
        "fieldname": "ewaybill",
        "label": "e-Waybill No.",
        "fieldtype": "Data",
        "depends_on": "eval: doc.docstatus === 1 || doc.ewaybill",
        "allow_on_submit": 1,
        "insert_after": "customer_name",
        "translatable": 0,
        "no_copy": 1,
    },
]

E_WAYBILL_SI_FIELDS = [
    {
        "fieldname": "transporter_info",
        "label": "Transporter Info",
        "fieldtype": "Section Break",
        "insert_after": "language",
        "collapsible": 1,
        "collapsible_depends_on": "transporter",
        "print_hide": 1,
    },
    {
        "fieldname": "transporter",
        "label": "Transporter",
        "fieldtype": "Link",
        "insert_after": "transporter_info",
        "options": "Supplier",
        "print_hide": 1,
    },
    {
        "fieldname": "driver",
        "label": "Driver",
        "fieldtype": "Link",
        "insert_after": "gst_transporter_id",
        "options": "Driver",
        "print_hide": 1,
    },
    {
        "fieldname": "lr_no",
        "label": "Transport Receipt No",
        "fieldtype": "Data",
        "insert_after": "driver",
        "print_hide": 1,
        "translatable": 0,
        "length": 30,
    },
    {
        "fieldname": "vehicle_no",
        "label": "Vehicle No",
        "fieldtype": "Data",
        "insert_after": "lr_no",
        "print_hide": 1,
        "translatable": 0,
        "length": 15,
    },
    {
        "fieldname": "transporter_col_break",
        "fieldtype": "Column Break",
        "insert_after": "distance",
    },
    {
        "fieldname": "transporter_name",
        "label": "Transporter Name",
        "fieldtype": "Small Text",
        "insert_after": "transporter_col_break",
        "fetch_from": "transporter.name",
        "read_only": 1,
        "print_hide": 1,
        "translatable": 0,
    },
    {
        "fieldname": "driver_name",
        "label": "Driver Name",
        "fieldtype": "Small Text",
        "insert_after": "mode_of_transport",
        "fetch_from": "driver.full_name",
        "print_hide": 1,
        "translatable": 0,
    },
    {
        "fieldname": "lr_date",
        "label": "Transport Receipt Date",
        "fieldtype": "Date",
        "insert_after": "driver_name",
        "default": "Today",
        "print_hide": 1,
    },
    *E_WAYBILL_DN_FIELDS,
]

E_WAYBILL_FIELDS = {
    "Sales Invoice": E_WAYBILL_SI_FIELDS,
    "Delivery Note": E_WAYBILL_DN_FIELDS,
}
