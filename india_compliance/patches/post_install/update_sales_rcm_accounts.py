import frappe
from frappe.utils import flt
from erpnext.setup.setup_wizard.operations.taxes_setup import (
    make_taxes_and_charges_template,
)

from india_compliance.gst_india.overrides.company import add_accounts_in_gst_settings
from india_compliance.gst_india.utils import get_gst_accounts_by_type

SALES_RCM_ACCOUNTS = [
    "Output Tax CGST RCM",
    "Output Tax SGST RCM",
    "Output Tax IGST RCM",
]


TEMPLATE = [
    {
        "title": "Output GST RCM In-state",
        "taxes": [
            {
                "account_head": {
                    "account_name": "sgst_account",
                    "tax_rate": 9.0,
                    "account_type": "account_type",
                },
                "description": "SGST",
            },
            {
                "account_head": {
                    "account_name": "cgst_account",
                    "tax_rate": 9.0,
                    "account_type": "Tax",
                },
                "description": "CGST",
            },
            {
                "account_head": {
                    "account_name": "Output Tax SGST RCM",
                    "tax_rate": -9.0,
                    "account_type": "Tax",
                },
                "description": "SGST RCM",
            },
            {
                "account_head": {
                    "account_name": "Output Tax CGST RCM",
                    "tax_rate": -9.0,
                    "account_type": "Tax",
                },
                "description": "CGST RCM",
            },
        ],
        "tax_category": "Reverse Charge In-State",
    },
    {
        "title": "Output GST RCM Out-state",
        "taxes": [
            {
                "account_head": {
                    "account_name": "igst_account",
                    "tax_rate": 18.0,
                    "account_type": "Tax",
                },
                "description": "IGST",
            },
            {
                "account_head": {
                    "account_name": "Output Tax IGST RCM",
                    "tax_rate": -18.0,
                    "account_type": "Tax",
                },
                "description": "IGST RCM",
            },
        ],
        "tax_category": "Reverse Charge Out-State",
    },
]


def execute():
    # skipping setup for new installations
    if frappe.db.get_all(
        "GST Account", {"account_type": ["=", "Sales Reverse Charge"]}
    ):
        return

    companies = frappe.get_all("Company", filters={"country": "India"}, pluck="name")
    for company in companies:
        # skipping if account already exists
        if frappe.get_all(
            "Account",
            {
                "company": company,
                "account_name": ("in", SALES_RCM_ACCOUNTS),
            },
        ):
            continue

        gst_accounts = get_gst_accounts_by_type(company, "Output")
        account_names = get_account_names(gst_accounts)
        tax_categories = get_tax_categories()
        gst_rate = get_default_gst_rate(gst_accounts)

        for template in TEMPLATE:
            template["tax_category"] = tax_categories.get(template["tax_category"], "")

            for row in template.get("taxes"):
                taxes = row["account_head"]
                update_account_name(gst_accounts, account_names, taxes)
                update_tax_rate(gst_rate, taxes)

            make_taxes_and_charges_template(
                company, "Sales Taxes and Charges Template", template
            )

        update_gst_settings(company)


def get_default_gst_rate(gst_accounts):
    gst_rate = (
        frappe.db.get_value(
            "Sales Taxes and Charges",
            filters={"account_head": gst_accounts.igst_account},
            fieldname="rate",
        )
        or 18
    )

    return gst_rate


def get_account_names(gst_accounts):
    accounts = frappe.get_all(
        "Account",
        filters={"name": ["in", gst_accounts.values()]},
        fields=["name", "account_name", "root_type"],
    )

    account_names = {}
    for account in accounts:
        account_names[account.name] = account

    return account_names


def update_account_name(gst_accounts, account_names, taxes):
    template_account = taxes["account_name"]
    if template_account in SALES_RCM_ACCOUNTS:
        return

    account_info = account_names.get(gst_accounts.get(template_account))

    if not account_info:
        return

    taxes["account_name"] = account_info.account_name
    taxes["root_type"] = account_info.root_type


def update_tax_rate(gst_rate, taxes):
    if gst_rate == 18:
        return

    rate = gst_rate if taxes["tax_rate"] == 18 else flt(gst_rate / 2, 3)

    taxes["tax_rate"] = rate


def get_tax_categories():
    rcm_tax_categories = {}

    tax_categories = frappe.get_all(
        "Tax Category",
        filters={"is_reverse_charge": 1, "disabled": 0},
        fields=["name", "is_inter_state"],
    )

    for category in tax_categories:
        rcm_tax_category = (
            "Reverse Charge Out-State"
            if category.is_inter_state
            else "Reverse Charge In-State"
        )
        rcm_tax_categories[rcm_tax_category] = category.name

    return rcm_tax_categories


def update_gst_settings(company):
    gst_settings = frappe.get_cached_doc("GST Settings")
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
                    SALES_RCM_ACCOUNTS,
                ),
            },
            ["account_name", "name"],
            as_list=1,
        )
    )

    add_accounts_in_gst_settings(
        company,
        SALES_RCM_ACCOUNTS,
        gst_accounts,
        existing_account_list,
        gst_settings,
        "Sales Reverse Charge",
    )

    gst_settings.save()
