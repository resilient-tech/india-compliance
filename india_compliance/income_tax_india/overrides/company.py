import frappe
from frappe.utils import getdate

from india_compliance.gst_india.overrides.company import create_default_company_account


def make_company_fixtures(doc, method=None):
    if not frappe.flags.country_change or doc.country != "India":
        return

    create_company_fixtures(doc.name)


def create_company_fixtures(company):
    company = company or frappe.db.get_value("Global Defaults", None, "default_company")
    create_tds_account(company)

    # create records for Tax Withholding Category
    create_or_update_tax_withholding_category(company)


def create_tds_account(company):
    create_default_company_account(
        company, account_name="TDS Payable", parent="Duties and Taxes"
    )


def create_or_update_tax_withholding_category(company):
    accounts = []
    tds_account = frappe.get_value(
        "Account", {"account_name": "TDS Payable", "company": company}, "name"
    )

    if company and tds_account:
        accounts.append({"company": company, "account": tds_account})

    categories = get_tds_category_details(accounts)

    for category_doc in categories:
        existing_category_list = frappe.get_all(
            "Tax Withholding Category",
            {
                "tds_section": category_doc.get("tds_section"),
                "entity_type": category_doc.get("entity_type"),
            },
            pluck="name",
        )
        if not existing_category_list:
            doc = frappe.get_doc(category_doc)
            doc.insert(ignore_if_duplicate=True, ignore_mandatory=True)

        else:
            for category_name in existing_category_list:
                update_existing_tax_withholding_category(
                    category_doc, category_name, company
                )


def update_existing_tax_withholding_category(category_doc, category_name, company):
    doc = frappe.get_doc("Tax Withholding Category", category_name)

    # add company account if not present for the category
    for row in doc.get("accounts"):
        if row.company == company:
            break

    else:
        accounts = category_doc.get("accounts")
        if accounts:
            doc.extend("accounts", accounts)

    # add rates if not present for the dates
    largest_date = None
    for doc_row in doc.get("rates"):
        if not largest_date:
            largest_date = getdate(doc_row.get("to_date"))

        if getdate(doc_row.get("to_date")) > largest_date:
            largest_date = getdate(doc_row.get("to_date"))

    for cat_row in category_doc["rates"]:
        if largest_date and getdate(cat_row.get("from_date")) < largest_date:
            continue

        doc.append("rates", cat_row)

    # accounts table is mandatory
    doc.flags.ignore_mandatory = True

    doc.save()


def get_tds_category_details(accounts):
    tds_details = []
    tds_rules = frappe.get_file_json(
        frappe.get_app_path(
            "india_compliance", "income_tax_india", "data", "tds_details.json"
        )
    )
    for rule in tds_rules:
        rates = get_prospective_tds_rates(rule["rates"])
        if not rates:
            continue
        tds_details.append(
            {
                "name": rule.get("name"),
                "category_name": rule.get("category_name"),
                "doctype": "Tax Withholding Category",
                "accounts": accounts,
                "tds_section": rule.get("tds_section"),
                "entity_type": rule.get("entity_type"),
                "round_off_tax_amount": rule.get("round_off_tax_amount"),
                "consider_party_ledger_amount": rule.get(
                    "consider_party_ledger_amount"
                ),
                "tax_on_excess_amount": rule.get("tax_on_excess_amount"),
                "rates": rates,
            }
        )

    return tds_details


def get_prospective_tds_rates(rates):
    """
    Ensure TDS rules are not created for the historical rates
    """
    rate_list = []
    today = getdate()
    for row in rates:
        if today <= getdate(row["to_date"]):
            rate_list.append(row)

    return rate_list
