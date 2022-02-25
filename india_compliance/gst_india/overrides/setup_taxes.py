import json

import frappe
from erpnext.setup.setup_wizard.operations.taxes_setup import \
    from_detailed_data
from frappe import _

from ..setup import update_regional_tax_settings


def setup_taxes_and_charges(company_name: str, country: str):
    if not frappe.db.exists("Company", company_name):
        frappe.throw(
            _("Company {} does not exist yet. Taxes setup aborted.").format(
                company_name
            )
        )

    file_path = file_path = frappe.get_app_path(
        "india_compliance", "gst_india", "data", "india_tax.json"
    )
    with open(file_path, "r") as json_file:
        tax_data = json.load(json_file)

    country_wise_tax = tax_data.get(country)

    if not country_wise_tax:
        return

    from_detailed_data(company_name, country_wise_tax)
    update_regional_tax_settings(company_name)
