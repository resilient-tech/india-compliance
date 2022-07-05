import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import now_datetime, nowdate

from india_compliance.gst_india.constants.custom_fields import (
    CUSTOM_FIELDS,
    E_INVOICE_FIELDS,
    E_WAYBILL_FIELDS,
    SALES_REVERSE_CHARGE_FIELDS,
)
from india_compliance.gst_india.setup.property_setters import get_property_setters
from india_compliance.gst_india.utils import get_data_file_path, toggle_custom_fields

AFTER_INSTALL_PATCHES = ("overrides_tax_settings_in_accounts_settings",)


def after_install():
    # Validation ignored for faster creation
    # Will not fail if a core field with same name already exists (!)
    # Will update a custom field if it already exists
    for fields in (
        CUSTOM_FIELDS,
        SALES_REVERSE_CHARGE_FIELDS,
        E_INVOICE_FIELDS,
        E_WAYBILL_FIELDS,
    ):
        create_custom_fields(fields, ignore_validate=True)

    create_property_setters()
    create_address_template()
    setup_default_gst_settings()
    create_hsn_codes()
    run_after_install_patches()


def create_property_setters():
    for property_setter in get_property_setters():
        frappe.make_property_setter(property_setter)


def create_address_template():
    if frappe.db.exists("Address Template", "India"):
        return

    address_html = frappe.read_file(
        get_data_file_path("address_template.html"), raise_not_found=True
    )

    frappe.get_doc(
        {
            "doctype": "Address Template",
            "country": "India",
            "is_default": 1,
            "template": address_html,
        }
    ).insert(ignore_permissions=True)


def create_hsn_codes():
    user = frappe.session.user
    now = now_datetime()

    fields = [
        "name",
        "creation",
        "modified",
        "owner",
        "modified_by",
        "hsn_code",
        "description",
    ]

    hsn_codes = [
        [
            code["hsn_code"],
            now,
            now,
            user,
            user,
            code["hsn_code"],
            code["description"],
        ]
        for code in frappe.get_file_json(get_data_file_path("hsn_codes.json"))
    ]

    frappe.db.bulk_insert(
        "GST HSN Code",
        fields,
        hsn_codes,
        ignore_duplicates=True,
        chunk_size=20_000,
    )


def setup_default_gst_settings():
    settings = frappe.get_doc("GST Settings")
    settings.db_set(
        {
            "hsn_wise_tax_breakup": 1,
            "enable_reverse_charge_in_sales": 0,
            "validate_hsn_code": 1,
            "min_hsn_digits": 6,
            "enable_e_waybill": 1,
            "e_waybill_threshold": 50000,
            # Default API Settings
            "fetch_e_waybill_data": 1,
            "attach_e_waybill_print": 1,
            "auto_generate_e_waybill": 1,
            "auto_generate_e_invoice": 1,
            "e_invoice_applicable_from": nowdate(),
            "auto_fill_party_info": 1,
        }
    )

    # Hide the fields as not enabled by default
    for fields in (E_INVOICE_FIELDS, SALES_REVERSE_CHARGE_FIELDS):
        toggle_custom_fields(fields, False)


def run_after_install_patches():
    print("\nPatching default settings...")
    for patch in AFTER_INSTALL_PATCHES:
        frappe.get_attr(f"india_compliance.patches.post_install.{patch}.execute")()
