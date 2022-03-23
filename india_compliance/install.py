import click

import frappe

from india_compliance.gst_india.setup import after_install as setup_gst
from india_compliance.income_tax_india.setup import after_install as setup_income_tax

# list of filenames (without extension) in sequence of execution
POST_INSTALL_PATCHES = (
    # ERPNext
    "setup_gst_india",
    "sync_india_custom_fields",
    "set_missing_gst_hsn_code",
    "set_gst_category",
    "update_gst_category",
    "add_export_type_field_in_party_master",
    "add_einvoice_status_field",
    "update_tax_category_for_rcm",
    "add_company_link_to_einvoice_settings",
    # India Compliance
    "remove_consumer_gst_category",
    "update_gst_accounts",
    "migrate_e_invoice_settings_to_gst_settings",
)


def after_install():
    setup_income_tax()
    setup_gst()
    run_post_install_patches()
    click.secho("\nThank you for installing India Compliance!", fg="green")


def run_post_install_patches():
    if not frappe.db.exists("Company", {"country": "India"}):
        return

    print("Running post-install patches")
    for patch in POST_INSTALL_PATCHES:
        frappe.get_attr(f"india_compliance.patches.post_install.{patch}.execute")()
