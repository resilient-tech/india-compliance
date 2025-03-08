from india_compliance.income_tax_india.constants.custom_fields import CUSTOM_FIELDS
from india_compliance.utils.custom_fields import get_custom_fields_creator

_create_custom_fields = get_custom_fields_creator("Income Tax India")


def after_install():
    create_custom_fields()


def create_custom_fields():
    _create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
