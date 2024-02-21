import frappe
from frappe.utils import get_link_to_form


def on_change(doc, method=None):
    frappe.cache.delete_value("tax_withholding_accounts")


def get_tax_withholding_accounts(company):
    def _get_tax_withholding_accounts():
        return set(
            frappe.get_all(
                "Tax Withholding Account", pluck="account", filters={"company": company}
            )
        )

    return frappe.cache.hget(
        "tax_withholding_accounts", company, generator=_get_tax_withholding_accounts
    )


def validate(doc, method=None):

    name = frappe.db.exists(
        "Tax Withholding Category",
        {
            "tds_section": doc.tds_section,
            "entity_type": doc.entity_type,
            "name": ("!=", doc.name),
        },
    )

    if not name:
        return

    frappe.throw(
        f'{get_link_to_form("Tax Withholding Category",name)} already exists for the TDS section - {doc.tds_section} and entity type - {doc.entity_type}.'
    )
