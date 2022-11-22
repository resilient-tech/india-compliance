import click

import frappe
from frappe.custom.doctype.custom_field.custom_field import (
    create_custom_fields as _create_custom_fields,
)
from frappe.utils import now_datetime, nowdate

from india_compliance.gst_india.constants import GST_UOMS
from india_compliance.gst_india.constants.custom_fields import (
    CUSTOM_FIELDS,
    E_INVOICE_FIELDS,
    E_WAYBILL_FIELDS,
    SALES_REVERSE_CHARGE_FIELDS,
)
from india_compliance.gst_india.setup.property_setters import get_property_setters
from india_compliance.gst_india.utils import get_data_file_path, toggle_custom_fields


def after_install():
    create_custom_fields()
    create_property_setters()
    create_address_template()
    set_default_gst_settings()
    set_default_accounts_settings()
    create_hsn_codes()


def create_custom_fields():
    # Validation ignored for faster creation
    # Will not fail if a core field with same name already exists (!)
    # Will update a custom field if it already exists
    _create_custom_fields(
        _get_custom_fields_to_create(
            CUSTOM_FIELDS,
            SALES_REVERSE_CHARGE_FIELDS,
            E_INVOICE_FIELDS,
            E_WAYBILL_FIELDS,
        ),
        ignore_validate=True,
    )


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


def set_default_gst_settings():
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

    map_default_uoms(settings)


def set_default_accounts_settings():
    """
    Accounts Settings overridden by India Compliance

    - Determine Address Tax Category From:
        This is overriden to be Billing Address, since that's the correct
        address for determining GST applicablility

    - Automatically Add Taxes and Charges from Item Tax Template:
        This is overriden to be "No". Item Tax Templates are designed to have
        all GST Accounts and are primarily used for selection of tax rate.
        Setting this to "Yes" can lead to all GST Accounts being included in taxes.
    """

    show_accounts_settings_override_warning()

    frappe.db.set_value(
        "Accounts Settings",
        None,
        {
            "determine_address_tax_category_from": "Billing Address",
            "add_taxes_from_item_tax_template": 0,
        },
    )

    frappe.db.set_default("add_taxes_from_item_tax_template", 0)


def show_accounts_settings_override_warning():
    """
    Show warning if Determine Address Tax Category From is set to something
    other than Billing Address.

    Note:
    Warning cannot be reliably shown for `add_taxes_from_item_tax_template`,
    since it defaults to `1`
    """

    address_for_tax_category = frappe.db.get_value(
        "Accounts Settings",
        "Accounts Settings",
        "determine_address_tax_category_from",
    )

    if not address_for_tax_category or address_for_tax_category == "Billing Address":
        return

    click.secho(
        "Overriding Accounts Settings: Determine Address Tax Category From",
        fg="yellow",
        bold=True,
    )

    click.secho(
        "This is being set as Billing Address, since that's the correct "
        "address for determining GST applicablility.",
        fg="yellow",
    )


def _get_custom_fields_to_create(*custom_fields_list):
    result = {}

    for custom_fields in custom_fields_list:
        for doctypes, fields in custom_fields.items():
            if isinstance(fields, dict):
                fields = [fields]

            result.setdefault(doctypes, []).extend(fields)

    return result


def map_default_uoms(settings=None):
    def _is_uom_mapped():
        return next(
            (True for mapping in settings.gst_uom_mapping if mapping.uom == uom), False
        )

    if not settings or settings.name != "GST Settings":
        settings = frappe.get_doc("GST Settings")

    for uom, gst_uom in GST_UOMS.items():
        if not frappe.db.exists("UOM", uom) or _is_uom_mapped():
            continue

        settings.append("gst_uom_mapping", {"uom": uom, "gst_uom": gst_uom})

    for row in settings.gst_uom_mapping:
        row.db_update()
