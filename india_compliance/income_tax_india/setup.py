import frappe

from india_compliance.income_tax_india.constants import MSME_PAYMENT_DAYS, MSME_PAYMENT_TERMS_TEMPLATE
from india_compliance.income_tax_india.constants.custom_fields import CUSTOM_FIELDS
from india_compliance.utils.custom_fields import get_custom_fields_creator

_create_custom_fields = get_custom_fields_creator("Income Tax India")


def after_install():
    create_custom_fields()
    create_msme_payment_terms_template()


def create_custom_fields():
    _create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)


def create_msme_payment_terms_template():
    if frappe.db.exists("Payment Terms Template", MSME_PAYMENT_TERMS_TEMPLATE):
        return

    frappe.get_doc(
        {
            "doctype": "Payment Terms Template",
            "template_name": MSME_PAYMENT_TERMS_TEMPLATE,
            "terms": [
                {
                    "invoice_portion": 100,
                    "due_date_based_on": "Day(s) after invoice date",
                    "credit_days": MSME_PAYMENT_DAYS,
                }
            ],
        }
    ).insert(ignore_permissions=True)
