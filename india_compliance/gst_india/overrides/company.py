import json

import frappe
from erpnext.setup.setup_wizard.operations.taxes_setup import \
    from_detailed_data
from frappe import _

from ..setup import update_regional_tax_settings
from ..utils import read_data_file


def delete_gst_settings_for_company(doc, method):
    if not frappe.flags.country_change or doc.country != "India":
        return

    gst_settings = frappe.get_doc("GST Settings")

    gst_settings.gst_accounts = [
        row for row in gst_settings.get("gst_accounts", []) if row.company != doc.name
    ]

    gst_settings.save()


def create_default_tax_templates(doc, method=None):
    if not frappe.flags.country_change:
        return

    make_default_tax_templates(doc.name, doc.country)


@frappe.whitelist()
def make_default_tax_templates(company: str, country: str):
    if country != "India":
        return

    if not frappe.db.exists("Company", company):
        frappe.throw(
            _("Company {0} does not exist yet. Taxes setup aborted.").format(company)
        )

    default_taxes = json.loads(read_data_file("tax_defaults.json"))
    from_detailed_data(company, default_taxes)
    update_regional_tax_settings(company)


def update_accounts_settings_for_taxes(doc, method=None):
    if doc.country != "India" or frappe.db.count("Company") > 1:
        return

    frappe.db.set_value(
        "Accounts Settings", None, "add_taxes_from_item_tax_template", 0
    )
