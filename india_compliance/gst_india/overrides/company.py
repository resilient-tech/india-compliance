import json

import frappe
from erpnext.setup.setup_wizard.operations.taxes_setup import from_detailed_data
from frappe import _

from ..setup import update_regional_tax_settings
from ..utils import read_data_file


def delete_gst_settings_for_company(doc, method):
    if not frappe.flags.country_change or doc.country != "India":
        return

    gst_settings = frappe.get_doc("GST Settings")
    records_to_delete = []

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
        frappe.throw(_(f"Company {company} does not exist yet. Taxes setup aborted."))

    tax_data = json.loads(read_data_file("india_tax.json"))
    country_wise_tax = tax_data.get(country)
    if not country_wise_tax:
        return

    from_detailed_data(company, country_wise_tax)
    update_regional_tax_settings(company)
