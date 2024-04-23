import frappe
from frappe.utils import flt
from erpnext.setup.setup_wizard.operations.taxes_setup import (
    make_taxes_and_charges_template,
)

from india_compliance.gst_india.overrides.company import add_accounts_in_gst_settings
from india_compliance.gst_india.utils import get_gst_accounts_by_type
from india_compliance.gst_india.utils.__init__ import get_data_file_path

SALES_RCM_TEMPLATES = ["Output GST RCM In-state", "Output GST RCM Out-state"]
SALES_RCM_ACCOUNTS = [
    "Output Tax CGST RCM",
    "Output Tax SGST RCM",
    "Output Tax IGST RCM",
]


def execute():
    # skipping setup for new installations
    if frappe.db.get_all(
        "GST Account", {"account_type": ["=", "Sales Reverse Charge"]}
    ):
        return

    companies = frappe.get_all("Company", filters={"country": "India"}, pluck="name")
    for company in companies:
        # determinig default gst rate
        output_igst_account = get_gst_accounts_by_type(company, "Output").igst_account

        default_gst_rate = frappe.db.get_value(
            "Sales Taxes and Charges",
            filters={"account_head": output_igst_account},
            fieldname="rate",
        )

        create_default_sales_rcm_templates(company, default_gst_rate)
        update_gst_settings(company)
        update_item_tax_template(company)


def create_default_sales_rcm_templates(company, gst_rate):
    default_taxes = frappe.get_file_json(get_data_file_path("tax_defaults.json"))
    sales_tax_templates = (
        default_taxes.get("chart_of_accounts").get("*").get("sales_tax_templates")
    )
    sales_rcm_tax_templates = []
    for template in sales_tax_templates:
        if template.get("title") in SALES_RCM_TEMPLATES:
            sales_rcm_tax_templates.append(template)

    for template in sales_rcm_tax_templates:
        for row in template.get("taxes"):
            if gst_rate == 18:
                continue

            rate = (
                gst_rate
                if row["account_head"]["tax_rate"] == 18
                else flt(gst_rate / 2, 3)
            )

            row["account_head"]["tax_rate"] = rate

        make_taxes_and_charges_template(
            company, "Sales Taxes and Charges Template", template
        )


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


def update_item_tax_template(company):
    gst_accounts = get_gst_accounts_by_type(
        company, "Sales Reverse Charge", throw=False
    )

    if not gst_accounts:
        return

    item_tax_templates = frappe.get_all(
        "Item Tax Template",
        {"company": company},
        pluck="name",
    )

    for template_name in item_tax_templates:
        doc = frappe.get_doc("Item Tax Template", template_name)
        existing_account_list = []

        if not doc.gst_rate:
            continue

        for tax in doc.taxes:
            existing_account_list.append(tax.tax_type)

        for type, account in gst_accounts.items():
            if not account:
                continue

            if account in existing_account_list:
                continue

            tax_rate = (
                doc.gst_rate if type == "igst_account" else doc.gst_rate / 2
            ) * -1
            doc.append("taxes", {"tax_type": account, "tax_rate": tax_rate})

        doc.save()
