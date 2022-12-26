from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from india_compliance.income_tax_india.constants.custom_fields import CUSTOM_FIELDS
from india_compliance.patches.post_install.update_e_invoice_fields_and_logs import (
    delete_custom_fields,
)


def after_install():
    create_custom_fields(CUSTOM_FIELDS, update=True)


def before_uninstall():
    delete_custom_fields(CUSTOM_FIELDS)
