import click

import frappe

from india_compliance.gst_india.constants import BUG_REPORT_URL
from india_compliance.gst_india.setup import after_install as setup_gst
from india_compliance.income_tax_india.setup import after_install as setup_income_tax

# list of filenames (without extension) in sequence of execution
POST_INSTALL_PATCHES = (
    ## ERPNext
    "setup_custom_fields_for_gst",
    "set_gst_category",
    "update_gst_category",
    "add_einvoice_status_field",
    "update_tax_category_for_rcm",
    "add_company_link_to_einvoice_settings",
    "update_state_code_for_daman_and_diu",
    "update_gst_accounts",  # this is an India Compliance patch, but needs priority
    "update_itc_amounts",
    ## India Compliance
    "create_company_fixtures",
    "merge_utgst_account_into_sgst_account",
    "remove_consumer_gst_category",
    "migrate_e_invoice_settings_to_gst_settings",
    "update_reverse_charge_and_export_type",
    "update_gstin_and_gst_category",
    "update_e_invoice_fields_and_logs",
    "set_default_gst_settings",
    "remove_deprecated_docs",
    "remove_old_fields",
    "update_custom_role_for_e_invoice_summary",
)


def after_install():
    try:
        print("Setting up Income Tax...")
        setup_income_tax()

        print("Setting up GST...")
        setup_gst()
        disable_ic_account_page()

        print("Patching Existing Data...")
        run_post_install_patches()

    except Exception as e:
        click.secho(
            "Installation for India Compliance failed due to an error."
            " Please try re-installing the app or"
            f" report the issue on {BUG_REPORT_URL} if not resolved.",
            fg="bright_red",
        )
        raise e

    click.secho("Thank you for installing India Compliance!", fg="green")


def run_post_install_patches():
    if not frappe.db.exists("Company", {"country": "India"}):
        return

    frappe.flags.in_patch = True

    try:
        for patch in POST_INSTALL_PATCHES:
            frappe.get_attr(f"india_compliance.patches.post_install.{patch}.execute")()

    finally:
        frappe.flags.in_patch = False


def disable_ic_account_page():
    """
    Disable the India Compliance Account Page if API secret is set in frappe.conf
    """

    if not frappe.conf.ic_api_secret or frappe.db.exists(
        "Custom Role", {"page": "india-compliance-account"}
    ):
        return

    frappe.get_doc(doctype="Custom Role", page="india-compliance-account").insert()
