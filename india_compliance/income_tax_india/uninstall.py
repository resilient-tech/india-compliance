from india_compliance.gst_india.utils.custom_fields import delete_custom_fields
from india_compliance.income_tax_india.constants.custom_fields import CUSTOM_FIELDS


def before_uninstall():
    delete_custom_fields(CUSTOM_FIELDS)
