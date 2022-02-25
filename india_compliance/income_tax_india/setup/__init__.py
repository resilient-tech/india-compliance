import frappe
from erpnext.accounts.utils import FiscalYearError, get_fiscal_year
from frappe.custom.doctype.custom_field.custom_field import \
    create_custom_fields as add_custom_fields
from frappe.utils import today

from .custom_fields import CUSTOM_FIELDS
from .salary_components import SALARY_COMPONENTS
from .tds_details import TDS_RULES


def setup_income_tax_india():
    add_custom_fields(CUSTOM_FIELDS, update=True)
    add_gratuity_rule()

    companies = frappe.get_all("Company", filters={"country": "India"}, pluck="name")
    if not companies:
        return

    for company in companies:
        add_company_fixtures(company)


def add_gratuity_rule():
    # Standard Indain Gratuity Rule
    if not frappe.db.exists("DocType", "Gratuity Rule") or frappe.db.exists(
        "Gratuity Rule", "Indian Standard Gratuity Rule"
    ):
        return

    rule = frappe.new_doc("Gratuity Rule")
    rule.name = "Indian Standard Gratuity Rule"
    rule.calculate_gratuity_amount_based_on = "Current Slab"
    rule.work_experience_calculation_method = "Round Off Work Experience"
    rule.minimum_year_for_gratuity = 5

    fraction = 15 / 26
    rule.append(
        "gratuity_rule_slabs",
        {"from_year": 0, "to_year": 0, "fraction_of_applicable_earnings": fraction},
    )

    rule.flags.ignore_mandatory = True
    rule.save()


def add_company_fixtures(company=None):
    docs = []
    company = company or frappe.db.get_value("Global Defaults", None, "default_company")

    docs.extend(SALARY_COMPONENTS)
    set_tds_account(docs, company)

    for d in docs:
        try:
            doc = frappe.get_doc(d)
            doc.flags.ignore_permissions = True
            doc.insert()
        except (frappe.NameError, frappe.DuplicateEntryError):
            frappe.clear_messages()

    # create records for Tax Withholding Category
    set_tax_withholding_category(company)


def set_tds_account(docs, company):
    parent_account = frappe.db.get_value(
        "Account", filters={"account_name": "Duties and Taxes", "company": company}
    )
    if parent_account:
        docs.extend(
            [
                {
                    "doctype": "Account",
                    "account_name": "TDS Payable",
                    "account_type": "Tax",
                    "parent_account": parent_account,
                    "company": company,
                }
            ]
        )


def set_tax_withholding_category(company):
    accounts = []
    fiscal_year_details = None
    abbr = frappe.get_value("Company", company, "abbr")
    tds_account = frappe.get_value("Account", "TDS Payable - {0}".format(abbr), "name")

    if company and tds_account:
        accounts = [dict(company=company, account=tds_account)]

    try:
        fiscal_year_details = get_fiscal_year(today(), verbose=0)
    except FiscalYearError:
        pass

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

            if fiscal_year_details:
                # if fiscal year don't match with any of the already entered data, append rate row
                fy_exist = [
                    k
                    for k in doc.get("rates")
                    if k.get("from_date") <= fiscal_year_details[1]
                    and k.get("to_date") >= fiscal_year_details[2]
                ]
                if not fy_exist:
                    doc.append("rates", d.get("rates")[0])

            doc.flags.ignore_permissions = True
            doc.flags.ignore_validate = True
            doc.flags.ignore_mandatory = True
            doc.flags.ignore_links = True
            doc.save()


def get_tds_details(accounts, fiscal_year_details):
    tds_details = []
    for category in TDS_RULES:
        for i in TDS_RULES[category]:
            tds_details.append(
                {
                    "name": i[0],
                    "category_name": category,
                    "doctype": "Tax Withholding Category",
                    "accounts": accounts,
                    "rates": [
                        {
                            "from_date": fiscal_year_details[1],
                            "to_date": fiscal_year_details[2],
                            "tax_withholding_rate": i[1],
                            "single_threshold": i[2],
                            "cumulative_threshold": i[3],
                        }
                    ],
                }
            )
    return tds_details
