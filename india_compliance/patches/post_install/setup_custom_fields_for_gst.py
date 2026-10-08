import frappe
from frappe.query_builder.functions import Concat, Length

from india_compliance.utils.custom_fields import delete_old_fields


def execute():
    delete_tax_id_custom_field()
    set_correct_state_number()
    remove_shipping_fields_from_purchase_invoice()


def delete_tax_id_custom_field():
    # delete custom field tax_id if it exists
    # this field was move to core ERPNext
    delete_old_fields("tax_id", ("Sales Order", "Sales Invoice", "Delivery Note"))


def set_correct_state_number():
    # set correct state number for all states with single digit state number
    address = frappe.qb.DocType("Address")
    (
        frappe.qb.update(address)
        .set(address.gst_state_number, Concat("0", address.gst_state_number))
        .where(Length(address.gst_state_number) == 1)
        .run()
    )


def remove_shipping_fields_from_purchase_invoice():
    delete_old_fields(("port_code", "shipping_bill_number", "shipping_bill_date"), "Purchase Invoice")
