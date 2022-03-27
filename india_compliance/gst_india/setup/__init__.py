import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from india_compliance.gst_india.constants.custom_fields import CUSTOM_FIELDS
from india_compliance.gst_india.setup.property_setters import get_property_setters
from india_compliance.gst_india.utils import read_data_file


def after_install():
    create_custom_fields(CUSTOM_FIELDS, update=True)
    create_property_setters()
    create_address_template()
    frappe.enqueue(create_hsn_codes, now=frappe.flags.in_test)


def create_property_setters():
    for property_setter in get_property_setters():
        frappe.make_property_setter(property_setter)


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
        for code in json.loads(read_data_file(f"{code_type}s.json")):
            frappe.get_doc(
                {
                    "doctype": "GST HSN Code",
                    "description": code["description"],
                    "hsn_code": code[code_type],
                    "name": code[code_type],
                }
            ).db_insert(ignore_if_duplicate=True)
