import frappe

from india_compliance.gst_india.constants import STATE_NUMBERS


def get_property_setters():
    return [
        {
            "doctype": "Journal Entry",
            "fieldname": "voucher_type",
            "property": "options",
            "value": get_updated_options(
                "Journal Entry", "voucher_type", ["Reversal Of ITC"]
            ),
        },
        {
            "doctype": "Sales Invoice",
            "fieldname": "naming_series",
            "property": "options",
            "value": get_updated_options(
                "Sales Invoice",
                "naming_series",
                ["SINV-.YY.-", "SRET-.YY.-", ""],
                prepend=True,
            ),
        },
        {
            "doctype": "Purchase Invoice",
            "fieldname": "naming_series",
            "property": "options",
            "value": get_updated_options(
                "Purchase Invoice",
                "naming_series",
                ["PINV-.YY.-", "PRET-.YY.-", ""],
                prepend=True,
            ),
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
            "property": "options_for_india",
            "value": "\n".join(STATE_NUMBERS.keys()),
        },
        {
            "doctype": "Address",
            "fieldname": "state",
            "property": "mandatory_depends_on",
            "value": "eval: doc.country == 'India'",
        },
    ]


def get_updated_options(doctype, fieldname, options, prepend=False):
    existing_options = frappe.get_meta(doctype).get_options(fieldname).split("\n")
    if prepend:
        options = options + existing_options
    else:
        options = existing_options + options

    return "\n".join(options)
