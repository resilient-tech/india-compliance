import os

import frappe

from india_compliance.gst_india.setup import after_install as setup_gst_india
from india_compliance.income_tax_india.setup import (
    after_install as setup_income_tax_india,
)


def after_install():
    setup_income_tax_india()
    setup_gst_india()
    run_post_install_patches()
    print("\nThank you for installing India Compliance!")


def run_post_install_patches():
    if not frappe.db.exists("Company", {"country": "India"}):
        return

    for patch in os.listdir(
        frappe.get_app_path("india_compliance", "patches/post_install")
    ):
        if not patch.endswith(".py") or patch == "__init__.py":
            continue

        frappe.get_attr(f"india_compliance.patches.post_install.{patch[:-3]}.execute")()
