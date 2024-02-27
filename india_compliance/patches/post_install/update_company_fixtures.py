import frappe
from frappe.query_builder.functions import IfNull
from erpnext.setup.setup_wizard.operations.taxes_setup import get_or_create_tax_group

from india_compliance.gst_india.overrides.company import (
    make_default_customs_accounts,
    make_default_gst_expense_accounts,
    make_default_tax_templates,
)
from india_compliance.income_tax_india.constants import TDS_ENTITY_TYPE, TDS_SECTIONS
from india_compliance.income_tax_india.overrides.company import (
    create_company_fixtures as create_income_tax_fixtures,
)


def execute():
    company_list = frappe.get_all(
        "Company", filters={"country": "India"}, pluck="name", order_by="lft asc"
    )
    set_section_and_entity_type_in_tax_withholding_category()  # execute before creating fixtures

    for company in company_list:
        # Income Tax fixtures

        create_income_tax_fixtures(company)

        # GST fixtures
        update_root_for_rcm(company)
        if not frappe.db.exists("GST Account", {"company": company}):
            make_default_tax_templates(company)

        make_default_customs_accounts(company)
        make_default_gst_expense_accounts(company)


def update_root_for_rcm(company):
    # Root type for RCM had been updated to "Liability".
    # This will ensure DuplicateEntryError is not raised for RCM accounts.

    # Hardcoded for exact account names only
    rcm_accounts = frappe.get_all(
        "Account",
        filters={
            "root_type": "Asset",
            "account_name": ("like", "Input Tax _GST RCM"),
            "company": company,
        },
        pluck="name",
    )

    if not rcm_accounts:
        return

    output_account = frappe.db.get_value(
        "Account",
        {"account_name": ("like", "Output Tax _GST"), "company": company},
        ["parent_account", "root_type"],
        as_dict=True,
    )

    if not output_account:
        parent_account = get_or_create_tax_group(company, "Liability")
        output_account = {
            "parent_account": parent_account,
            "root_type": "Liability",
        }

    # update reverse charge accounts
    frappe.db.set_value(
        "Account",
        {"name": ("in", rcm_accounts)},
        output_account,
        update_modified=False,
    )


def set_section_and_entity_type_in_tax_withholding_category():
    doctype = frappe.qb.DocType("Tax Withholding Category")
    categories = (
        frappe.qb.from_(doctype)
        .select(doctype.name)
        .where(IfNull(doctype.tds_section, "") == "")
        .where(IfNull(doctype.entity_type, "") == "")
        .run(pluck=True)
    )

    for category_name in categories:
        splitted_name = category_name.split(" - ")
        # old naming [TDS - SECTION - ENTITY]
        if len(splitted_name) < 3:
            continue

        if splitted_name[1] in TDS_SECTIONS and splitted_name[-1] in TDS_ENTITY_TYPE:
            (
                frappe.qb.update(doctype)
                .set("tds_section", splitted_name[1])
                .set("entity_type", splitted_name[-1])
                .where(doctype.name == category_name)
                .run()
            )
