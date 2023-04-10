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

    fiscal_year_details = get_current_fiscal_year()
    docs = get_tds_details(accounts, fiscal_year_details)

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

            if accounts:
                doc.append("accounts", accounts[0])

            # if fiscal year doesn't match with any of the already entered data,
            # append rate row
            if not next(
                (
                    row
                    for row in doc.get("rates")
                    if row.get("from_date") <= fiscal_year_details[0]
                    and row.get("to_date") >= fiscal_year_details[1]
                ),
                None,
            ):
                doc.append("rates", d.get("rates")[0])

            doc.flags.ignore_permissions = True
            doc.flags.ignore_validate = True
            doc.flags.ignore_mandatory = True
            doc.flags.ignore_links = True
            doc.save()


def get_tds_details(accounts, fiscal_year_details):
    tds_details = []
    tds_rules = frappe.get_file_json(
        frappe.get_app_path(
            "india_compliance", "income_tax_india", "data", "tds_details.json"
        )
    )

    for category in tds_rules:
        for rule in tds_rules[category]:
            tds_details.append(
                {
                    "name": rule[0],
                    "category_name": category,
                    "doctype": "Tax Withholding Category",
                    "accounts": accounts,
                    "rates": [
                        {
                            "from_date": fiscal_year_details[0],
                            "to_date": fiscal_year_details[1],
                            "tax_withholding_rate": rule[1],
                            "single_threshold": rule[2],
                            "cumulative_threshold": rule[3],
                        }
                    ],
                }
            )
    return tds_details


def get_current_fiscal_year():
    today = getdate()
    start_date_year = today.year if today.month >= 4 else today.year - 1

    return (
        getdate(f"{start_date_year}-04-01"),
        getdate(f"{start_date_year + 1}-03-31"),
    )
