import frappe


def get_property_setters():
    return [
        get_options_property_setter(
            "Journal Entry",
            "voucher_type",
            ["Reversal Of ITC"],
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
            "doctype": "e-Waybill Log",
            "doctype_or_field": "DocType",
            "property": "default_print_format",
            "value": "e-Waybill",
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
            "value": "1",
        },
        {
            "doctype": "Accounts Settings",
            "fieldname": "add_taxes_from_item_tax_template",
            "property": "read_only",
            "value": "1",
        },
        {
            "doctype": "Accounts Settings",
            "fieldname": "tax_settings_section",
            "property": "label",
            "value": "Tax Settings (Overridden by India Compliance)",
        },
        {
            "doctype": "Accounts Settings",
            "fieldname": "tax_settings_section",
            "property": "collapsible",
            "value": "1",
        },
        {
            "doctype": "Purchase Reconciliation Tool",
            "doctype_or_field": "DocType",
            "property": "default_email_template",
            "value": "Purchase Reconciliation",
        },
        *TRANSPORTER_NAME_PROPERTIES,
        *LR_NO_PROPERTIES,
        *LR_DATE_PROPERTIES,
    ]


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


TRANSPORTER_NAME_PROPERTIES = [
    {
        "doctype_or_field": "DocField",
        "doctype": "Purchase Receipt",
        "fieldname": "transporter_name",
        "property": "fieldtype",
        "property_type": "Select",
        "value": "Small Text",
    },
    {
        "doctype_or_field": "DocField",
        "doctype": "Purchase Receipt",
        "fieldname": "transporter_name",
        "property": "fetch_from",
        "property_type": "Small Text",
        "value": "transporter.supplier_name",
    },
    {
        "doctype_or_field": "DocField",
        "doctype": "Purchase Receipt",
        "fieldname": "transporter_name",
        "property": "no_copy",
        "property_type": "Check",
        "value": "1",
    },
    {
        "doctype_or_field": "DocField",
        "doctype": "Purchase Receipt",
        "fieldname": "transporter_name",
        "property": "print_hide",
        "property_type": "Check",
        "value": "1",
    },
    {
        "doctype_or_field": "DocField",
        "doctype": "Purchase Receipt",
        "fieldname": "transporter_name",
        "property": "read_only",
        "property_type": "Check",
        "value": "1",
    },
]

LR_NO_PROPERTIES = [
    {
        "doctype_or_field": "DocField",
        "doctype": "Purchase Receipt",
        "fieldname": "lr_no",
        "property": "label",
        "property_type": "Data",
        "value": "Transport Receipt No",
    },
    {
        "doctype_or_field": "DocField",
        "doctype": "Purchase Receipt",
        "fieldname": "lr_no",
        "property": "print_hide",
        "property_type": "Check",
        "value": "1",
    },
    {
        "doctype_or_field": "DocField",
        "doctype": "Purchase Receipt",
        "fieldname": "lr_no",
        "property": "length",
        "property_type": "Int",
        "value": "30",
    },
]


LR_DATE_PROPERTIES = [
    {
        "doctype_or_field": "DocField",
        "doctype": "Purchase Receipt",
        "fieldname": "lr_date",
        "property": "label",
        "property_type": "Data",
        "value": "Transport Receipt Date",
    },
    {
        "doctype_or_field": "DocField",
        "doctype": "Purchase Receipt",
        "fieldname": "lr_date",
        "property": "print_hide",
        "property_type": "Check",
        "value": "1",
    },
    {
        "doctype_or_field": "DocField",
        "doctype": "Purchase Receipt",
        "fieldname": "lr_date",
        "property": "default",
        "property_type": "Text",
        "value": "Today",
    },
]
