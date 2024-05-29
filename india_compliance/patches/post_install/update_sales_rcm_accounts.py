import frappe
from frappe.utils import flt
from erpnext.setup.setup_wizard.operations.taxes_setup import (
    make_tax_category,
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
                    "account_type": "Tax",
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
    if frappe.db.exists("GST Account", {"account_type": ["=", "Sales Reverse Charge"]}):
        return

    companies = frappe.get_all("Company", filters={"country": "India"}, pluck="name")
    for company in companies:
        # skipping if account already exists
        if frappe.db.exists(
            "Account",
            {
                "company": company,
                "account_name": ("in", SALES_RCM_ACCOUNTS),
            },
        ):
            continue

        output_gst_accounts = get_gst_accounts_by_type(company, "Output", throw=False)

        if not output_gst_accounts:
            continue

        setup_rcm_template(company, output_gst_accounts)
        update_gst_settings(company)


def setup_rcm_template(company, output_gst_accounts):
    account_name_map = get_account_name_map(output_gst_accounts)
    tax_category_map = get_tax_category_map()
    gst_rate = get_default_gst_rate(output_gst_accounts)

    for template in TEMPLATE:
        template["tax_category"] = tax_category_map.get(template["tax_category"])

        for row in template.get("taxes"):
            taxes = row["account_head"]
            update_account_name(output_gst_accounts, account_name_map, taxes)
            update_tax_rate(gst_rate, taxes)

        make_taxes_and_charges_template(
            company, "Sales Taxes and Charges Template", template
        )


def get_default_gst_rate(output_gst_accounts):
    gst_rate = (
        frappe.db.get_value(
            "Sales Taxes and Charges",
            filters={
                "account_head": output_gst_accounts.igst_account,
                "parenttype": "Sales Taxes and Charges Template",
            },
            fieldname="rate",
        )
        or 18
    )

    return gst_rate


def get_account_name_map(output_gst_accounts):
    accounts = frappe.get_all(
        "Account",
        filters={"name": ["in", list(output_gst_accounts.values())]},
        fields=["name", "account_name", "root_type"],
    )

    account_names = {account.name: account for account in accounts}

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
    # update tax_rate for row
    if gst_rate == 18:
        return

    is_interstate_tax = taxes["tax_rate"] == 18

    rate = gst_rate if is_interstate_tax else flt(gst_rate / 2, 3)

    taxes["tax_rate"] = rate


def get_tax_category_map():
    rcm_tax_categories = {
        "Reverse Charge In-State": "",
        "Reverse Charge Out-State": "",
    }

    for category in rcm_tax_categories.keys():
        # Handle interstate tax category
        get_or_create_tax_category(rcm_tax_categories, category)

    return rcm_tax_categories


def get_or_create_tax_category(rcm_tax_categories, category):
    filters = {"is_reverse_charge": 1, "disabled": 0}
    is_interstate = 1 if category == "Reverse Charge Out-State" else 0
    filters["is_interstate"] = is_interstate

    template_name = frappe.db.get_value("Tax Category", filters=filters)

    if not template_name:
        make_tax_category({"title": category, **filters})
        template_name = category

    rcm_tax_categories[category] = template_name


def update_gst_settings(company):
    gst_settings = frappe.get_cached_doc("GST Settings")

    existing_account_list = [
        account.get(key)
        for account in gst_settings.get("gst_accounts")
        for key in ["cgst_account", "sgst_account", "igst_account"]
    ]

    gst_accounts = frappe._dict(
        frappe.get_all(
            "Account",
            {
                "company": company,
                "account_name": ("in", SALES_RCM_ACCOUNTS),
            },
            ["account_name", "name"],
            as_list=1,
        )
    )

    if len(gst_accounts) != 3:
        return

    add_accounts_in_gst_settings(
        company,
        SALES_RCM_ACCOUNTS,
        gst_accounts,
        existing_account_list,
        gst_settings,
        "Sales Reverse Charge",
    )

    gst_settings.save()
