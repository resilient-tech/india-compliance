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
    set_tax_withholding_category(company)


def create_tds_account(company):
    create_default_company_account(
        company, account_name="TDS Payable", parent="Duties and Taxes"
    )


def set_tax_withholding_category(company):
    accounts = []
    abbr = frappe.get_value("Company", company, "abbr")
    tds_account = frappe.get_value("Account", "TDS Payable - {0}".format(abbr), "name")

    if company and tds_account:
        accounts.append({"company": company, "account": tds_account})

    today = getdate()
    fiscal_year_details = get_all_fiscal_year()

    for year in fiscal_year_details:
        start_date = getdate(f"1-4-{year}")
        end_date = getdate(f"31-3-{int(year)+1}")
        if today > end_date:
            continue
        docs = get_tds_details(accounts, year)
        for d in docs:
            if not frappe.db.exists("Tax Withholding Category", d.get("name")):
                doc = frappe.get_doc(d)
                doc.flags.ignore_validate = True
                doc.flags.ignore_permissions = True
                doc.flags.ignore_mandatory = True
                doc.insert()
            else:
                doc = frappe.get_doc(
                    "Tax Withholding Category", d.get("name"), for_update=True
                )

                if accounts and not d.get("accounts"):
                    doc.append("accounts", accounts[0])

                # if fiscal year doesn't match with any of the already entered data,
                # append rate row
                if not next(
                    (
                        row
                        for row in doc.get("rates")
                        if row.get("from_date") <= start_date
                        and row.get("to_date") >= end_date
                    ),
                    None,
                ):
                    doc.append("rates", d.get("rates")[0])
                doc.section = d.get("section")
                doc.entity_type = d.get("entity_type")
                doc.flags.ignore_permissions = True
                doc.flags.ignore_validate = True
                doc.flags.ignore_mandatory = True
                doc.flags.ignore_links = True
                doc.save()


def get_tds_details(accounts, year):
    tds_details = []
    tds_rules = frappe.get_file_json(
        frappe.get_app_path(
            "india_compliance", "income_tax_india", "data", "tds_details.json"
        )
    )
    for category in tds_rules[year]:
        for rule in tds_rules[year][category]:
            tds_details.append(
                {
                    "name": f"TDS - {rule['section']} - {rule['entity_type']}",
                    "category_name": category,
                    "doctype": "Tax Withholding Category",
                    "accounts": accounts,
                    "section": rule["section"],
                    "entity_type": rule["entity_type"],
                    "rates": [
                        {
                            "from_date": getdate(f"1-4-{year}"),
                            "to_date": getdate(f"31-3-{int(year)+1}"),
                            "tax_withholding_rate": rule["tax_withholding_rate"],
                            "single_threshold": rule["single_threshold"],
                            "cumulative_threshold": rule["cumulative_threshold"],
                        }
                    ],
                }
            )

    return tds_details


def get_all_fiscal_year():
    year_list = []
    tds_rules = frappe.get_file_json(
        frappe.get_app_path(
            "india_compliance", "income_tax_india", "data", "tds_details.json"
        )
    )
    for year in tds_rules:
        year_list.append(year)

    return year_list
