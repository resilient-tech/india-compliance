import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from india_compliance.gst_india.constants.custom_fields import (
    CUSTOM_FIELDS,
    REVERSE_CHARGE_FIELD,
)
from india_compliance.gst_india.constants.e_invoice import E_INVOICE_FIELDS
from india_compliance.gst_india.constants.e_waybill import E_WAYBILL_FIELDS
from india_compliance.gst_india.setup.property_setters import get_property_setters
from india_compliance.gst_india.utils import read_data_file


def after_install():
    # Validation ignored for faster creation
    # Will not fail if a core field with same name already exists (!)
    # Will update a custom field if it already exists
    for fileds in (
        CUSTOM_FIELDS,
        REVERSE_CHARGE_FIELD,
        E_INVOICE_FIELDS,
        E_WAYBILL_FIELDS,
    ):
        create_custom_fields(fileds, ignore_validate=True)

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
