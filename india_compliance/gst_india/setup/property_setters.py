import frappe

from india_compliance.gst_india.constants import STATE_NUMBERS


def get_property_setters():
    return [
        get_naming_series_property(
            "Journal Entry",
            "voucher_type",
            ["Reversal Of ITC"],
            prepend=False,
        ),
        get_naming_series_property(
            "Delivery Note",
            "naming_series",
            ["DN-.YY.-", "DRET-.YY.-", ""],
        ),
        get_naming_series_property(
            "Sales Invoice",
            "naming_series",
            ["SINV-.YY.-", "SRET-.YY.-", ""],
        ),
        get_naming_series_property(
            "Purchase Invoice",
            "naming_series",
            ["PINV-.YY.-", "PRET-.YY.-", ""],
        ),
        {
            "doctype": "Address",
            "fieldname": "state",
            "property": "fieldtype",
            "value": "Autocomplete",
        },
        {
            "doctype": "Address",
            "fieldname": "state",
            "property": "options_for_india",
            "value": "\n".join(STATE_NUMBERS.keys()),
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
                "eval: doc.country == 'India' && frappe.boot.gst_settings &&"
                " (frappe.boot.gst_settings.enable_e_invoice ||"
                " frappe.boot.gst_settings.enable_e_waybill)"
            ),
        },
        {
            "doctype": "e-Waybill Log",
            "doctype_or_field": "DocType",
            "property": "default_print_format",
            "value": "e-Waybill",
        },
        {
            "doc_type": "Address",
            "doctype_or_field": "DocType",
            "property": "quick_entry",
            "property_type": "Check",
            "value": "1",
        },
    ]


def get_naming_series_property(doctype, fieldname, new_options, prepend=True):
    existing_options = frappe.get_meta(doctype).get_options(fieldname).split("\n")
    if prepend:
        options = new_options + existing_options
    else:
        options = existing_options + new_options

    options = "\n".join(options)

    return {
        "doctype": doctype,
        "fieldname": fieldname,
        "property": "options",
        "value": options,
    }
