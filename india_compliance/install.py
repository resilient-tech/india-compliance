import os

import frappe

from india_compliance.gst_india.setup import after_install as setup_gst
from india_compliance.income_tax_india.setup import after_install as setup_income_tax

# list of filenames (without extension) in sequence of execution
POST_INSTALL_PATCHES = ("remove_consumer_gst_category",)


def after_install():
    setup_income_tax()
    setup_gst()
    run_post_install_patches()
    print("\nThank you for installing India Compliance!")


def run_post_install_patches():
    if not frappe.db.exists("Company", {"country": "India"}):
        return

    for patch in POST_INSTALL_PATCHES:
        frappe.get_attr(f"india_compliance.patches.post_install.{patch}.execute")()
