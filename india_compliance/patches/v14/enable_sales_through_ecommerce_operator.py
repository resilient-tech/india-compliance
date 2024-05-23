import frappe

from india_compliance.patches.post_install.set_default_gst_settings import (
    POSTING_DATE_CONDITION,
)


def execute():
    if not frappe.db.exists(
        "Sales Invoice",
        {"ecommerce_gstin": ("not in", ("", None)), **POSTING_DATE_CONDITION},
    ):
        return

    frappe.db.set_single_value(
        "GST Settings", "enable_sales_through_ecommerce_operators", 1
    )
