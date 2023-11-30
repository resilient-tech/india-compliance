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
        {
            "doctype_or_field": "DocType",
            "doctype": "Purchase Receipt",
            "property": "field_order",
            "property_type": "Data",
            "value": '["supplier_section", "column_break0", "title", "naming_series", "supplier", "supplier_name", "ewaybill", "supplier_delivery_note", "column_break1", "posting_date", "posting_time", "set_posting_time", "column_break_12", "company", "apply_putaway_rule", "is_return", "return_against", "accounting_dimensions_section", "cost_center", "dimension_col_break", "project", "currency_and_price_list", "currency", "conversion_rate", "column_break2", "buying_price_list", "price_list_currency", "plc_conversion_rate", "ignore_pricing_rule", "sec_warehouse", "scan_barcode", "column_break_31", "set_warehouse", "set_from_warehouse", "col_break_warehouse", "rejected_warehouse", "is_subcontracted", "supplier_warehouse", "items_section", "items", "section_break0", "total_qty", "total_net_weight", "column_break_43", "base_total", "base_net_total", "column_break_27", "total", "net_total", "taxes_charges_section", "tax_category", "taxes_and_charges", "shipping_col", "shipping_rule", "column_break_53", "incoterm", "named_place", "taxes_section", "taxes", "totals", "base_taxes_and_charges_added", "base_taxes_and_charges_deducted", "base_total_taxes_and_charges", "column_break3", "taxes_and_charges_added", "taxes_and_charges_deducted", "total_taxes_and_charges", "section_break_46", "base_grand_total", "base_rounding_adjustment", "base_rounded_total", "base_in_words", "column_break_50", "grand_total", "rounding_adjustment", "rounded_total", "in_words", "disable_rounded_total", "section_break_42", "apply_discount_on", "base_discount_amount", "column_break_44", "additional_discount_percentage", "discount_amount", "sec_tax_breakup", "other_charges_calculation", "pricing_rule_details", "pricing_rules", "raw_material_details", "get_current_stock", "supplied_items", "address_and_contact_tab", "section_addresses", "supplier_address", "address_display", "supplier_gstin", "gst_category", "col_break_address", "contact_person", "contact_display", "contact_mobile", "contact_email", "section_break_98", "shipping_address", "column_break_100", "shipping_address_display", "billing_address_section", "billing_address", "column_break_104", "billing_address_display", "company_gstin", "place_of_supply", "terms_tab", "tc_name", "terms", "more_info_tab", "status_section", "status", "column_break4", "per_billed", "per_returned", "subscription_detail", "auto_repeat", "printing_settings", "letter_head", "group_same_items", "column_break_97", "select_print_heading", "language", "transporter_info", "transporter", "gst_transporter_id", "driver", "lr_no", "vehicle_no", "distance", "column_break5", "transporter_name", "mode_of_transport", "driver_name", "lr_date", "gst_vehicle_type", "additional_info_section", "instructions", "is_internal_supplier", "represents_company", "inter_company_reference", "column_break_131", "remarks", "range", "amended_from", "is_old_subcontracting_flow", "other_details", "connections_tab", "is_reverse_charge"]',
        },
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
