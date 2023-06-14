import frappe

from india_compliance.gst_india.constants.custom_fields import (
    SALES_REVERSE_CHARGE_FIELDS,
)
from india_compliance.gst_india.utils.custom_fields import toggle_custom_fields

# Enable setting only if transaction exists in last 3 years.
POSTING_DATE_CONDITION = {
    "posting_date": (">", "2019-04-01"),
}


def execute():
    new_settings = {}
    enable_overseas_transactions(new_settings)
    enable_reverse_charge_in_sales(new_settings)
    enable_e_waybill_from_dn(new_settings)

    if new_settings:
        frappe.db.set_single_value("GST Settings", new_settings)


def enable_e_waybill_from_dn(settings):
    if frappe.db.exists(
        "Delivery Note",
        {"ewaybill": ("not in", ("", None)), **POSTING_DATE_CONDITION},
    ):
        return

    settings["enable_e_waybill_from_dn"] = 1


def enable_overseas_transactions(settings):
    for doctype in ("Sales Invoice", "Purchase Invoice"):
        if frappe.db.exists(
            doctype,
            {"gst_category": ("in", {"Overseas", "SEZ"}), **POSTING_DATE_CONDITION},
        ):
            settings["enable_overseas_transactions"] = 1
            return


def enable_reverse_charge_in_sales(settings):
    if not frappe.db.exists(
        "Sales Invoice",
        {"is_reverse_charge": 1, **POSTING_DATE_CONDITION},
    ):
        return

    settings["enable_reverse_charge_in_sales"] = 1
    toggle_custom_fields(SALES_REVERSE_CHARGE_FIELDS, True)
