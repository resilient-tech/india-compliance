import frappe

from india_compliance.gst_india.overrides.invoice import update_taxable_values
from india_compliance.gst_india.overrides.transaction import (
    set_place_of_supply,
    validate_gst_accounts,
    validate_hsn_code,
    validate_items,
    validate_mandatory_fields,
)


def validate_gst_challan(doc, method=None):
    country, gst_category = frappe.get_cached_value(
        "Company", doc.company, ("country", "gst_category")
    )

    if country != "India" or gst_category == "Unregistered":
        return

    if validate_items(doc) is False:
        # If there are no GST items, then no need to proceed further
        return

    set_place_of_supply(doc)
    update_taxable_values(doc)
    validate_mandatory_fields(doc, ("company_gstin",))
    validate_gst_accounts(doc)
    validate_hsn_code(doc)

    enable_e_waybill, enable_e_waybill_from_dn = frappe.get_cached_value(
        "GST Settings", "GST Settings", ["enable_e_waybill", "enable_e_waybill_from_dn"]
    )

    if not enable_e_waybill or not enable_e_waybill_from_dn:
        return

    validate_mandatory_fields(doc, ("shipping_address_name",))
