import frappe


def on_change(doc, method=None):
    frappe.cache.delete_value("tax_withholding_accounts")


def get_tax_withholding_accounts(company):
    def _get_tax_withholding_accounts():
        return set(
            frappe.get_all(
                "Tax Withholding Account", pluck="account", filters={"company": company}
            )
        )

    return frappe.cache.hget(
        "tax_withholding_accounts", company, generator=_get_tax_withholding_accounts
    )
