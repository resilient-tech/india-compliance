import json

import frappe
from erpnext.setup.setup_wizard.operations.taxes_setup import \
    from_detailed_data
from frappe import _

from india_compliance.gst_india.utils import read_data_file


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
    update_gst_settings(company)


def update_accounts_settings_for_taxes(doc, method=None):
    if doc.country != "India" or frappe.db.count("Company") > 1:
        return

    frappe.db.set_value(
        "Accounts Settings", None, "add_taxes_from_item_tax_template", 0
    )


def update_gst_settings(company):
    # Will only add default GST accounts if present
    input_account_names = ["Input Tax CGST", "Input Tax SGST", "Input Tax IGST"]
    output_account_names = ["Output Tax CGST", "Output Tax SGST", "Output Tax IGST"]
    rcm_accounts = ["Input Tax CGST RCM", "Input Tax SGST RCM", "Input Tax IGST RCM"]
    gst_settings = frappe.get_single("GST Settings")
    existing_account_list = []

    for account in gst_settings.get("gst_accounts"):
        for key in ["cgst_account", "sgst_account", "igst_account"]:
            existing_account_list.append(account.get(key))

    gst_accounts = frappe._dict(
        frappe.get_all(
            "Account",
            {
                "company": company,
                "account_name": (
                    "in",
                    input_account_names + output_account_names + rcm_accounts,
                ),
            },
            ["account_name", "name"],
            as_list=1,
        )
    )

    add_accounts_in_gst_settings(
        company, input_account_names, gst_accounts, existing_account_list, gst_settings,
        gst_account_type='Input'
    )
    add_accounts_in_gst_settings(
        company, output_account_names, gst_accounts, existing_account_list, gst_settings,
        gst_account_type='Output'
    )
    add_accounts_in_gst_settings(
        company,
        rcm_accounts,
        gst_accounts,
        existing_account_list,
        gst_settings,
        gst_account_type='Reverse Charge',
        is_reverse_charge=1
    )

    gst_settings.save()


def add_accounts_in_gst_settings(
    company,
    account_names,
    gst_accounts,
    existing_account_list,
    gst_settings,
    gst_account_type,
    is_reverse_charge=0
):
    accounts_not_added = 1
    for account in account_names:
        # Default Account Added does not exist
        if not gst_accounts.get(account):
            accounts_not_added = 0

        # Check if already added in GST Settings
        if gst_accounts.get(account) in existing_account_list:
            accounts_not_added = 0

    if accounts_not_added:
        gst_settings.append(
            "gst_accounts",
            {
                "company": company,
                "cgst_account": gst_accounts.get(account_names[0]),
                "sgst_account": gst_accounts.get(account_names[1]),
                "igst_account": gst_accounts.get(account_names[2]),
                "gst_account_type": gst_account_type,
                "is_reverse_charge_account": is_reverse_charge,
            },
        )
