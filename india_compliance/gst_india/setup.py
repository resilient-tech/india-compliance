import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import (
    create_custom_fields,
)
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from .utils import read_data_file
from .constants.custom_fields import CUSTOM_FIELDS


def after_install():
    create_custom_fields(CUSTOM_FIELDS, update=True)
    create_property_setters()
    create_address_template()
    frappe.enqueue(create_hsn_codes, now=frappe.flags.in_test)


def create_property_setters():
    options_to_add = [
        {
            "doctype": "Journal Entry",
            "fieldname": "voucher_type",
            "options_after": ["Reversal Of ITC"],
        },
        {
            "doctype": "Sales Invoice",
            "fieldname": "naming_series",
            "options_before": ["SINV-.YY.-", "SRET-.YY.-", ""],
        },
    ]

    for doc in options_to_add:
        existing_options = (
            frappe.get_meta(doc["doctype"]).get_options(doc["fieldname"]).split("\n")
        )
        make_property_setter(
            doc["doctype"],
            doc["fieldname"],
            "options",
            "\n".join(
                doc.get("options_before", [])
                + existing_options
                + doc.get("options_after", [])
            ),
            "Text",
        )


def create_address_template():
    if frappe.db.exists("Address Template", "India"):
        return

    address_html = read_data_file("address_template.html")

    frappe.get_doc(
        {
            "doctype": "Address Template",
            "country": "India",
            "is_default": 1,
            "template": address_html,
        }
    ).insert(ignore_permissions=True)


def create_hsn_codes():
    for code_type in ("hsn_code", "sac_code"):
        codes = json.loads(read_data_file(f"{code_type}s.json"))
        for code in codes:
            frappe.get_doc(
                {
                    "doctype": "GST HSN Code",
                    "description": code["description"],
                    "hsn_code": code[code_type],
                    "name": code[code_type],
                }
            ).db_insert(ignore_if_duplicate=True)


def update_regional_tax_settings(company):
    # Will only add default GST accounts if present
    input_account_names = ["Input Tax CGST", "Input Tax SGST", "Input Tax IGST"]
    output_account_names = ["Output Tax CGST", "Output Tax SGST", "Output Tax IGST"]
    rcm_accounts = ["Input Tax CGST RCM", "Input Tax SGST RCM", "Input Tax IGST RCM"]
    gst_settings = frappe.get_single("GST Settings")
    existing_account_list = []

    for account in gst_settings.get("gst_accounts"):
        for key in ["cgst_account", "sgst_account", "igst_account"]:
            existing_account_list.append(account.get(key))

    gst_accounts = frappe._dict(
        frappe.get_all(
            "Account",
            {
                "company": company,
                "account_name": (
                    "in",
                    input_account_names + output_account_names + rcm_accounts,
                ),
            },
            ["account_name", "name"],
            as_list=1,
        )
    )

    add_accounts_in_gst_settings(
        company, input_account_names, gst_accounts, existing_account_list, gst_settings
    )
    add_accounts_in_gst_settings(
        company, output_account_names, gst_accounts, existing_account_list, gst_settings
    )
    add_accounts_in_gst_settings(
        company,
        rcm_accounts,
        gst_accounts,
        existing_account_list,
        gst_settings,
        is_reverse_charge=1,
    )

    gst_settings.save()


def add_accounts_in_gst_settings(
    company,
    account_names,
    gst_accounts,
    existing_account_list,
    gst_settings,
    is_reverse_charge=0,
):
    accounts_not_added = 1

    for account in account_names:
        # Default Account Added does not exist
        if not gst_accounts.get(account):
            accounts_not_added = 0

        # Check if already added in GST Settings
        if gst_accounts.get(account) in existing_account_list:
            accounts_not_added = 0

    if accounts_not_added:
        gst_settings.append(
            "gst_accounts",
            {
                "company": company,
                "cgst_account": gst_accounts.get(account_names[0]),
                "sgst_account": gst_accounts.get(account_names[1]),
                "igst_account": gst_accounts.get(account_names[2]),
                "is_reverse_charge_account": is_reverse_charge,
            },
        )
