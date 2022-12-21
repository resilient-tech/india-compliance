import frappe

from india_compliance.gst_india.constants.custom_fields import (
    CUSTOM_FIELDS,
    E_INVOICE_FIELDS,
    E_WAYBILL_FIELDS,
    SALES_REVERSE_CHARGE_FIELDS,
)
from india_compliance.gst_india.setup import _get_custom_fields_map
from india_compliance.gst_india.setup.property_setters import get_property_setters
from india_compliance.patches.post_install.update_e_invoice_fields_and_logs import (
    delete_custom_fields as _delete_custom_fields,
)


def after_uninstall():
    delete_custom_fields()
    delete_property_setters()


def delete_custom_fields():
    _delete_custom_fields(
        _get_custom_fields_map(
            CUSTOM_FIELDS,
            SALES_REVERSE_CHARGE_FIELDS,
            E_INVOICE_FIELDS,
            E_WAYBILL_FIELDS,
        ),
        ignore_validate=True,
    )


def delete_property_setters():
    for property_setter in get_property_setters():
        keys_to_update = ["doc_type", "field_name", "property", "value"]
        filters = dict(zip(keys_to_update, list(property_setter.values())))
        frappe.db.delete("Property Setter", filters)
