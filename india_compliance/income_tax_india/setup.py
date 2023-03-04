from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from india_compliance.income_tax_india.constants.custom_fields import CUSTOM_FIELDS


def after_install():
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
