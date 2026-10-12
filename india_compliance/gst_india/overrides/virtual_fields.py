import frappe
from frappe.contacts.doctype.address.address import get_address_display

from india_compliance.gst_india.overrides.purchase_invoice import get_ineligibility_reason
from india_compliance.gst_india.overrides.transaction import (
    get_ecommerce_supply_type,
    get_gst_breakup_html,
)


def get_virtual_field_values(doc):
    values = {}

    for resolver in frappe.get_hooks("ic_virtual_field_resolvers").get(doc.doctype, []):
        values.update(frappe.get_attr(resolver)(doc))

    return values


def onload(doc, method=None):
    doc.set_onload("ic_virtual_fields", get_virtual_field_values(doc))


def before_print(doc, method=None, print_settings=None):
    doc.update(get_virtual_field_values(doc))


def resolve_gst_breakup(doc):
    return {"gst_breakup_table": get_gst_breakup_html(doc)}


def resolve_ecommerce_supply_type(doc):
    return {"ecommerce_supply_type": get_ecommerce_supply_type(doc)}


def resolve_address_displays(doc):
    address_fields = ("bill_from_address", "bill_to_address", "ship_from_address", "ship_to_address")
    addresses = {doc.get(field) for field in address_fields if doc.get(field)}
    displays = {address: get_address_display(address) for address in addresses}

    return {f"{field}_display": displays.get(doc.get(field)) for field in address_fields}


def resolve_ineligibility_reason(doc):
    return {"ineligibility_reason": get_ineligibility_reason(doc)}
