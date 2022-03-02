import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import (
    create_custom_fields,
)
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from .utils import read_data_file
from .constants.custom_fields import CUSTOM_FIELDS


def after_install():
    create_custom_fields(CUSTOM_FIELDS, update=True)
    create_property_setters()
    create_address_template()
    frappe.enqueue(create_hsn_codes, now=frappe.flags.in_test)


def create_property_setters():
    options_to_add = [
        {
            "doctype": "Journal Entry",
            "fieldname": "voucher_type",
            "options_after": ["Reversal Of ITC"],
        },
        {
            "doctype": "Sales Invoice",
            "fieldname": "naming_series",
            "options_before": ["SINV-.YY.-", "SRET-.YY.-", ""],
        },
    ]

    for doc in options_to_add:
        existing_options = (
            frappe.get_meta(doc["doctype"]).get_options(doc["fieldname"]).split("\n")
        )
        make_property_setter(
            doc["doctype"],
            doc["fieldname"],
            "options",
            "\n".join(
                doc.get("options_before", [])
                + existing_options
                + doc.get("options_after", [])
            ),
            "Text",
        )


def create_address_template():
    if frappe.db.exists("Address Template", "India"):
        return

    address_html = read_data_file("address_template.html")

    frappe.get_doc(
        {
            "doctype": "Address Template",
            "country": "India",
            "is_default": 1,
            "template": address_html,
        }
    ).insert(ignore_permissions=True)


def create_hsn_codes():
    for code_type in ("hsn_code", "sac_code"):
        codes = json.loads(read_data_file(f"{code_type}s.json"))
        for code in codes:
            frappe.get_doc(
                {
                    "doctype": "GST HSN Code",
                    "description": code["description"],
                    "hsn_code": code[code_type],
                    "name": code[code_type],
                }
            ).db_insert(ignore_if_duplicate=True)
