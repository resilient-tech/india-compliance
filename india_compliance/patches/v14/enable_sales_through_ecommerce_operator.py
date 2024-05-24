import frappe

from india_compliance.patches.post_install.set_default_gst_settings import (
    enable_sales_through_ecommerce_operators,
)


def execute():
    new_settings = {}

    enable_sales_through_ecommerce_operators(new_settings)

    if new_settings:
        frappe.db.set_single_value("GST Settings", new_settings)
