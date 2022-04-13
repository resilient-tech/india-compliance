import frappe

from india_compliance.gst_india.overrides.invoice import update_taxable_values
from india_compliance.gst_india.overrides.transaction import (
    is_indian_registered_company,
    set_place_of_supply,
    validate_gst_accounts,
    validate_hsn_code,
    validate_items,
    validate_mandatory_fields,
    validate_tax_accounts_for_non_gst,
)


def validate(doc, method=None):
    if not is_indian_registered_company(doc):
        return

    if validate_items(doc) is False:
        # If there are no GST items, then no need to proceed further
        validate_tax_accounts_for_non_gst(doc)
        return

    set_place_of_supply(doc)
    update_taxable_values(doc)
    validate_mandatory_fields(doc, ("company_gstin",))
    validate_gst_accounts(doc)
    validate_hsn_code(doc)

    enable_e_waybill_from_dn = frappe.get_cached_value(
        "GST Settings", "GST Settings", "enable_e_waybill_from_dn"
    )

    if not enable_e_waybill_from_dn:
        return

    validate_mandatory_fields(doc, ("shipping_address_name",))
