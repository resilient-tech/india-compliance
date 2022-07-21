import frappe
from frappe import _
from erpnext.setup.setup_wizard.operations.taxes_setup import from_detailed_data

from india_compliance.gst_india.utils import get_data_file_path


def delete_gst_settings_for_company(doc, method=None):
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

    frappe.has_permission("Company", ptype="write", doc=company, throw=True)

    default_taxes = frappe.get_file_json(get_data_file_path("tax_defaults.json"))
    from_detailed_data(company, default_taxes)
    update_gst_settings(company)


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
        company,
        input_account_names,
        gst_accounts,
        existing_account_list,
        gst_settings,
        "Input",
    )
    add_accounts_in_gst_settings(
        company,
        output_account_names,
        gst_accounts,
        existing_account_list,
        gst_settings,
        "Output",
    )
    add_accounts_in_gst_settings(
        company,
        rcm_accounts,
        gst_accounts,
        existing_account_list,
        gst_settings,
        "Reverse Charge",
    )

    gst_settings.save()


def add_accounts_in_gst_settings(
    company,
    account_names,
    gst_accounts,
    existing_account_list,
    gst_settings,
    account_type,
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
                "account_type": account_type,
            },
        )
