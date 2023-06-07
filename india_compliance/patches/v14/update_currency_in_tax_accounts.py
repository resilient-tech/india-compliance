import frappe

from india_compliance.gst_india.constants import GST_ACCOUNT_FIELDS


def execute():
    settings = frappe.get_doc("GST Settings")
    gst_accounts = get_all_gst_accounts(settings)

    if not gst_accounts:
        return

    default_currency = get_company_default_currency(gst_accounts)

    for account, company in gst_accounts.items():
        account_currency = frappe.db.get_value("Account", account, "account_currency")

        if account_currency:
            continue

        gl_currency = frappe.db.get_value(
            "GL Entry", {"account": account}, "account_currency"
        )

        if gl_currency and gl_currency != default_currency.get(company):
            continue

        frappe.db.set_value(
            "Account",
            account,
            "account_currency",
            default_currency.get(company),
            update_modified=False,
        )


def get_company_default_currency(company_accounts):
    default_currency = {}

    for company in set(company_accounts.values()):
        default_currency[company] = frappe.get_cached_value(
            "Company", company, "default_currency"
        )

    return default_currency


def get_all_gst_accounts(settings):
    accounts_dict = {}

    for row in settings.gst_accounts:
        for account in GST_ACCOUNT_FIELDS:
            if gst_account := row.get(account):
                accounts_dict[gst_account] = row.company

    return accounts_dict
