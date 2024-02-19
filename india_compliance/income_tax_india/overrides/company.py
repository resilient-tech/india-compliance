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

    tds_rules = get_tds_details(accounts)

    for rule in tds_rules:
        name = frappe.get_value(
            "Tax Withholding Category",
            {
                "tds_section": rule.get("tds_section"),
                "entity_type": rule.get("entity_type"),
            },
        )
        if not name:
            doc = frappe.get_doc(rule)
            doc.flags.ignore_validate = True
            doc.flags.ignore_permissions = True
            doc.flags.ignore_mandatory = True
            doc.insert()
        else:
            doc = frappe.get_doc("Tax Withholding Category", name, for_update=True)

            if accounts and not doc.get("accounts"):
                doc.append("accounts", accounts[0])

            for rate in rule.get("rates"):
                if not next(
                    (
                        row
                        for row in doc.get("rates")
                        if row.get("from_date") <= getdate(rate.get("from_date"))
                        and row.get("to_date") >= getdate(rate.get("to_date"))
                    ),
                    None,
                ):
                    doc.append("rates", rate)

            doc.tds_section = rule.get("tds_section")
            doc.entity_type = rule.get("entity_type")
            doc.flags.ignore_permissions = True
            doc.flags.ignore_validate = True
            doc.flags.ignore_mandatory = True
            doc.flags.ignore_links = True
            doc.save()


def get_tds_details(accounts):
    tds_details = []
    tds_rules = frappe.get_file_json(
        frappe.get_app_path(
            "india_compliance", "income_tax_india", "data", "tds_details.json"
        )
    )
    for rule in tds_rules:
        tds_details.append(
            {
                "name": rule["name"],
                "category_name": rule["category_name"],
                "doctype": "Tax Withholding Category",
                "accounts": accounts,
                "tds_section": rule["tds_section"],
                "entity_type": rule["entity_type"],
                "round_off_tax_amount": rule["round_off_tax_amount"],
                "consider_party_ledger_amount": rule["consider_party_ledger_amount"],
                "tax_on_excess_amount": rule["tax_on_excess_amount"],
                "rates": get_rate_list(rule["rates"]),
            }
        )

    return tds_details


def get_rate_list(rates):
    rate_list = []
    today = getdate()
    for i in rates:
        if today <= getdate(i["to_date"]):
            rate_list.append(i)
    return rate_list
