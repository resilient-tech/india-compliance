import click

import frappe

from india_compliance.gst_india.setup import after_install as setup_gst
from india_compliance.income_tax_india.setup import after_install as setup_income_tax

# list of filenames (without extension) in sequence of execution
POST_INSTALL_PATCHES = (
    # ERPNext
    "setup_custom_fields_for_gst",
    "set_gst_category",
    "update_gst_category",
    "add_einvoice_status_field",
    "update_tax_category_for_rcm",
    "add_company_link_to_einvoice_settings",
    "update_state_code_for_daman_and_diu"
    # India Compliance
    "create_company_fixtures",
    "merge_utgst_account_into_sgst_account",
    "remove_consumer_gst_category",
    "update_gst_accounts",
    "migrate_e_invoice_settings_to_gst_settings",
    "update_reverse_charge_and_export_type",
    "update_gstin_and_gst_category",
    "update_e_invoice_fields_and_logs",
    "delete_gst_e_invoice_print_format",
    "set_default_gst_settings",
    "remove_old_fields",
)


def after_install():
    setup_income_tax()
    setup_gst()
    run_post_install_patches()
    click.secho("Thank you for installing India Compliance!", fg="green")


def run_post_install_patches():
    if not frappe.db.exists("Company", {"country": "India"}):
        return

    print("\nPatching Existing Data...")
    for patch in POST_INSTALL_PATCHES:
        frappe.get_attr(f"india_compliance.patches.post_install.{patch}.execute")()
