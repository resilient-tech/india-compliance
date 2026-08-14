import frappe


def get_property_setters(*, include_defaults=False):
    properties = [
        {
            "doctype": "Purchase Invoice",
            "fieldname": "bill_no",
            "property": "mandatory_depends_on",
            "value": "eval: doc.gst_category !== 'Unregistered' && gst_settings.require_supplier_invoice_no === 1 && doc.company_gstin",
        },
        {
            "doctype": "Address",
            "fieldname": "state",
            "property": "fieldtype",
            "value": "Autocomplete",
        },
        {
            "doctype": "Address",
            "fieldname": "state",
            "property": "mandatory_depends_on",
            "value": "eval: doc.country == 'India'",
        },
        {
            "doctype": "Address",
            "fieldname": "pincode",
            "property": "mandatory_depends_on",
            "value": (
                "eval: doc.country == 'India' &&"
                "(gst_settings.enable_e_invoice || gst_settings.enable_e_waybill)"
            ),
        },
        {
            "doctype": "Address",
            "doctype_or_field": "DocType",
            "property": "quick_entry",
            "property_type": "Check",
            "value": "1",
        },
        {
            "doctype": "Accounts Settings",
            "fieldname": "determine_address_tax_category_from",
            "property": "read_only",
            "value": "0",
        },
        {
            "doctype": "Accounts Settings",
            "fieldname": "add_taxes_from_item_tax_template",
            "property": "read_only",
            "value": "1",
        },
        {
            "doctype": "Accounts Settings",
            "fieldname": "add_taxes_from_item_tax_template",
            "property": "description",
            "value": "Overridden by India Compliance",
        },
        {
            "doctype": "Accounts Settings",
            "fieldname": "tax_settings_section",
            "property": "label",
            "value": "Tax Settings",
        },
        {
            "doctype": "Accounts Settings",
            "fieldname": "tax_settings_section",
            "property": "collapsible",
            "value": "0",
        },
        {
            "doctype": "Subcontracting Receipt",
            "fieldname": "supplier_delivery_note",
            "property": "mandatory_depends_on",
            "value": "eval: gst_settings.require_supplier_invoice_no === 1 && doc.company_gstin",
        },
        {
            "doctype": "Asset Movement",
            "doctype_or_field": "DocType",
            "property": "autoname",
            "property_type": "Data",
            "value": "naming_series:",
        },
        {
            "doctype": "Asset Movement",
            "doctype_or_field": "DocType",
            "property": "naming_rule",
            "property_type": "Data",
            "value": 'By "Naming Series" field',
        },
        *PURCHASE_RECEIPT_PROPERTIES,
        *SUBCONTRACTING_RECEIPT_PROPERTIES,
        *ADDRESS_ALLOW_ON_SUBMIT_PROPERTIES,
        *get_transporter_properties(),
    ]

    if include_defaults:
        properties.extend(DEFAULT_PROPERTIES)

    return properties


def get_options_property_setter(doctype, fieldname, new_options, prepend=True):
    existing_options = frappe.get_meta(doctype).get_options(fieldname).split("\n")
    if prepend:
        options = new_options + existing_options
    else:
        options = existing_options + new_options

    # using dict.fromkeys to get unique ordered options
    # https://stackoverflow.com/a/53657523/4767738
    options = "\n".join(dict.fromkeys(options))

    return {
        "doctype": doctype,
        "fieldname": fieldname,
        "property": "options",
        "value": options,
    }


# Transporter details stay editable after submit until an e-Waybill is generated
ALLOW_ON_SUBMIT_PROPERTY = {
    "property": "allow_on_submit",
    "property_type": "Check",
    "value": "1",
}

EWAYBILL_READ_ONLY_PROPERTY = {
    "property": "read_only_depends_on",
    "property_type": "Code",
    "value": "eval: doc.ewaybill",
}

FETCH_IF_EMPTY_PROPERTY = {
    "property": "fetch_if_empty",
    "property_type": "Check",
    "value": "1",
}

TRANSPORTER_NAME_PROPERTIES = [
    {
        "doctype_or_field": "DocField",
        "fieldname": "transporter_name",
        "property": "fieldtype",
        "property_type": "Select",
        "value": "Small Text",
    },
    {
        "doctype_or_field": "DocField",
        "fieldname": "transporter_name",
        "property": "fetch_from",
        "property_type": "Small Text",
        "value": "transporter.supplier_name",
    },
    {
        "doctype_or_field": "DocField",
        "fieldname": "transporter_name",
        "property": "no_copy",
        "property_type": "Check",
        "value": "1",
    },
    {
        "doctype_or_field": "DocField",
        "fieldname": "transporter_name",
        "property": "print_hide",
        "property_type": "Check",
        "value": "1",
    },
    {
        "doctype_or_field": "DocField",
        "fieldname": "transporter_name",
        "property": "read_only",
        "property_type": "Check",
        "value": "1",
    },
]

LR_NO_PROPERTIES = [
    {
        "doctype_or_field": "DocField",
        "fieldname": "lr_no",
        "property": "label",
        "property_type": "Data",
        "value": "Transport Receipt No",
    },
    {
        "doctype_or_field": "DocField",
        "fieldname": "lr_no",
        "property": "print_hide",
        "property_type": "Check",
        "value": "1",
    },
    {
        "doctype_or_field": "DocField",
        "fieldname": "lr_no",
        "property": "length",
        "property_type": "Int",
        "value": "30",
    },
]


LR_DATE_PROPERTIES = [
    {
        "doctype_or_field": "DocField",
        "fieldname": "lr_date",
        "property": "label",
        "property_type": "Data",
        "value": "Transport Receipt Date",
    },
    {
        "doctype_or_field": "DocField",
        "fieldname": "lr_date",
        "property": "print_hide",
        "property_type": "Check",
        "value": "1",
    },
    {
        "doctype_or_field": "DocField",
        "fieldname": "lr_date",
        "property": "default",
        "property_type": "Text",
        "value": "Today",
    },
]

PURCHASE_RECEIPT_PROPERTIES = [
    {"doctype": "Purchase Receipt", **field}
    for field in TRANSPORTER_NAME_PROPERTIES + LR_NO_PROPERTIES + LR_DATE_PROPERTIES
]

SUBCONTRACTING_RECEIPT_PROPERTIES = [
    {"doctype": "Subcontracting Receipt", **field}
    for field in TRANSPORTER_NAME_PROPERTIES + LR_NO_PROPERTIES + LR_DATE_PROPERTIES
]

SALES_ADDRESS_FIELDS = (
    "customer_address",
    "address_display",
    "shipping_address_name",
    "shipping_address",
    "billing_address_gstin",
    "gst_category",
    "place_of_supply",
)

PURCHASE_ADDRESS_FIELDS = (
    "supplier_address",
    "address_display",
    "shipping_address",
    "shipping_address_display",
    "supplier_gstin",
    "gst_category",
    "place_of_supply",
)

ADDRESS_FIELDS_BY_DOCTYPE = {
    **dict.fromkeys(
        ("Quotation", "Sales Order", "Delivery Note", "Sales Invoice"),
        SALES_ADDRESS_FIELDS,
    ),
    **dict.fromkeys(
        ("Supplier Quotation", "Purchase Order", "Purchase Receipt", "Purchase Invoice"),
        PURCHASE_ADDRESS_FIELDS,
    ),
}

ADDRESS_ALLOW_ON_SUBMIT_PROPERTIES = [
    {
        "doctype": doctype,
        "fieldname": fieldname,
        "property": "allow_on_submit",
        "property_type": "Check",
        "value": "1",
    }
    for doctype, fieldnames in ADDRESS_FIELDS_BY_DOCTYPE.items()
    for fieldname in fieldnames
]


ERPNEXT_TRANSPORTER_FIELDS = {
    "Delivery Note": (
        "transporter",
        "transporter_name",
        "driver",
        "driver_name",
        "lr_no",
        "lr_date",
        "vehicle_no",
    ),
    "Purchase Receipt": ("transporter_name", "lr_no", "lr_date"),
    "Subcontracting Receipt": ("transporter_name", "lr_no", "lr_date"),
}

# fetched from transporter / driver needs fetch if empty.
ERPNEXT_FETCHED_TRANSPORTER_FIELDS = ("transporter_name", "driver_name")


def get_transporter_properties():
    properties = []

    for doctype, fieldnames in ERPNEXT_TRANSPORTER_FIELDS.items():
        for fieldname in fieldnames:
            field = {"doctype": doctype, "fieldname": fieldname}

            properties.append({**field, **ALLOW_ON_SUBMIT_PROPERTY})
            properties.append({**field, **EWAYBILL_READ_ONLY_PROPERTY})

            if fieldname in ERPNEXT_FETCHED_TRANSPORTER_FIELDS:
                properties.append({**field, **FETCH_IF_EMPTY_PROPERTY})

    return properties


# Customizable property setters that are set by default
DEFAULT_PROPERTIES = [
    # DEFAULTS #
    {
        "doctype": "e-Waybill Log",
        "doctype_or_field": "DocType",
        "property": "default_print_format",
        "value": "e-Waybill",
        "is_system_generated": 0,
    },
    {
        "doctype": "Purchase Reconciliation Tool",
        "doctype_or_field": "DocType",
        "property": "default_email_template",
        "value": "Purchase Reconciliation",
    },
    {
        "doctype": "GSTR 3B Report",
        "doctype_or_field": "DocType",
        "property": "default_print_format",
        "value": "GSTR-3B",
        "is_system_generated": 0,
    },
    # OPTIONS #
    get_options_property_setter(
        "Journal Entry",
        "voucher_type",
        ["Reversal Of ITC", "Reclaim of ITC Reversal"],
        prepend=False,
    ),
    get_options_property_setter(
        "Delivery Note",
        "naming_series",
        ["DN-.YY.-", "DRET-.YY.-", ""],
    ),
    get_options_property_setter(
        "Sales Invoice",
        "naming_series",
        ["SINV-.YY.-", "SRET-.YY.-", ""],
    ),
    get_options_property_setter(
        "Purchase Invoice",
        "naming_series",
        ["PINV-.YY.-", "PRET-.YY.-", ""],
    ),
    get_options_property_setter(
        "Purchase Receipt",
        "naming_series",
        ["PR-.YY.-", "PRRET-.YY.-", ""],
    ),
    get_options_property_setter(
        "Journal Entry Account",
        "reference_type",
        ["Bill of Entry"],
        prepend=False,
    ),
    get_options_property_setter(
        "Stock Entry",
        "naming_series",
        ["MAT-STE-"],
    ),
    get_options_property_setter(
        "Subcontracting Receipt",
        "naming_series",
        ["MAT-SCR-"],
    ),
]
