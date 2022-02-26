import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import \
    create_custom_fields as add_custom_fields
from frappe.custom.doctype.property_setter.property_setter import \
    make_property_setter
from frappe.permissions import add_permission, update_permission_property

from .custom_fields import CUSTOM_FIELDS


def setup_gst_india():
    add_custom_fields(CUSTOM_FIELDS, update=True)
    add_property_setters()
    add_permissions()
    add_custom_roles_for_reports()
    add_print_formats()
    add_address_template()
    update_accounts_settings_for_taxes()
    frappe.enqueue(add_hsn_sac_codes, now=frappe.flags.in_test)


def add_property_setters():
    options_to_update = [
        ["Journal Entry", "voucher_type", ["Reversal Of ITC"], []],
        ["Sales Invoice", "naming_series", [], ["SINV-.YY.-", "SRET-.YY.-", ""]],
        ["Purchase Invoice", "naming_series", [], ["PINV-.YY.-", "PRET-.YY.-", ""]],
    ]

    for doc in options_to_update:
        make_property_setter(
            doc[0],
            doc[1],
            "options",
            "\n".join(
                doc[2]
                + frappe.get_meta(doc[0]).get_options(doc[1]).split("\n")
                + doc[3]
            ),
        )


def add_permissions():
    for doctype in (
        "GST HSN Code",
        "GST Settings",
        "GSTR 3B Report",
        "Lower Deduction Certificate",
        "E Invoice Settings",
    ):
        add_permission(doctype, "All", 0)
        for role in ("Accounts Manager", "Accounts User", "System Manager"):
            add_permission(doctype, role, 0)
            update_permission_property(doctype, role, 0, "write", 1)
            update_permission_property(doctype, role, 0, "create", 1)

        if doctype == "GST HSN Code":
            for role in ("Item Manager", "Stock Manager"):
                add_permission(doctype, role, 0)
                update_permission_property(doctype, role, 0, "write", 1)
                update_permission_property(doctype, role, 0, "create", 1)


def add_custom_roles_for_reports():
    for report_name in (
        "GST Sales Register",
        "GST Purchase Register",
        "GST Itemised Sales Register",
        "GST Itemised Purchase Register",
        "Eway Bill",
        "E-Invoice Summary",
    ):

        if not frappe.db.get_value("Custom Role", dict(report=report_name)):
            frappe.get_doc(
                dict(
                    doctype="Custom Role",
                    report=report_name,
                    roles=[dict(role="Accounts User"), dict(role="Accounts Manager")],
                )
            ).insert()

    for report_name in ("Professional Tax Deductions", "Provident Fund Deductions"):

        if not frappe.db.get_value("Custom Role", dict(report=report_name)):
            frappe.get_doc(
                dict(
                    doctype="Custom Role",
                    report=report_name,
                    roles=[
                        dict(role="HR User"),
                        dict(role="HR Manager"),
                        dict(role="Employee"),
                    ],
                )
            ).insert()

    for report_name in ("HSN-wise-summary of outward supplies", "GSTR-1", "GSTR-2"):

        if not frappe.db.get_value("Custom Role", dict(report=report_name)):
            frappe.get_doc(
                dict(
                    doctype="Custom Role",
                    report=report_name,
                    roles=[
                        dict(role="Accounts User"),
                        dict(role="Accounts Manager"),
                        dict(role="Auditor"),
                    ],
                )
            ).insert()


def add_print_formats():
    for format in ["GST POS Invoice", "GST Tax Invoice", "GST E-Invoice"]:
        frappe.reload_doc("gst_india", "print_format", format)
        frappe.db.set_value("Print Format", format, "disabled", 0)


def add_address_template():
    if frappe.db.exists("Address Template", "India"):
        return

    path = frappe.get_app_path(
        "india_compliance", "gst_india", "data", "address_template.html"
    )
    with open(path, "r") as f:
        address_html = f.read()

    frappe.get_doc(
        {
            "doctype": "Address Template",
            "country": "India",
            "is_default": 1,
            "template": address_html,
        }
    ).insert(ignore_permissions=True)


def update_accounts_settings_for_taxes():
    if frappe.db.count("Company") == 1:
        frappe.db.set_value(
            "Accounts Settings", None, "add_taxes_from_item_tax_template", 0
        )


def add_hsn_sac_codes():
    if frappe.flags.in_test and frappe.flags.created_hsn_codes:
        return

    codes = ["hsn_code", "sac_code"]
    for code in codes:
        path = frappe.get_app_path(
            "india_compliance", "gst_india", "data", f"{code}_data.json"
        )
        with open(path, "r") as f:
            hsn_sac_codes = json.loads(f.read())
        create_hsn_codes(hsn_sac_codes, code_field=code)

    if frappe.flags.in_test:
        frappe.flags.created_hsn_codes = True


def create_hsn_codes(data, code_field):
    for d in data:
        hsn_code = frappe.new_doc("GST HSN Code")
        hsn_code.description = d["description"]
        hsn_code.hsn_code = d[code_field]
        hsn_code.name = d[code_field]
        try:
            hsn_code.db_insert()
        except frappe.DuplicateEntryError:
            pass


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
        # Default Account Added does not exists
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
