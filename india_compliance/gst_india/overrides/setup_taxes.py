import json

import frappe
from erpnext.setup.setup_wizard.operations.taxes_setup import \
    from_detailed_data
from frappe import _

from ..setup import update_regional_tax_settings
from ..utils import read_data_file


def setup_taxes_and_charges(company_name: str, country: str):
    if not frappe.db.exists("Company", company_name):
        frappe.throw(
            _("Company {} does not exist yet. Taxes setup aborted.").format(
                company_name
            )
        )

    tax_data = json.load(read_data_file("india_tax.json"))

    country_wise_tax = tax_data.get(country)

    if not country_wise_tax:
        return

    from_detailed_data(company_name, country_wise_tax)
    update_regional_tax_settings(company_name)
