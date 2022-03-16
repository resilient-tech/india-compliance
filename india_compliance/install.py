import click

import frappe

from india_compliance.gst_india.setup import after_install as setup_gst
from india_compliance.income_tax_india.setup import after_install as setup_income_tax

# list of filenames (without extension) in sequence of execution
POST_INSTALL_PATCHES = (
    # ERPNext
    "setup_gst_india",
    "sync_india_custom_fields",
    # India Compliance
    "remove_consumer_gst_category",
    "update_gst_accounts",
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
