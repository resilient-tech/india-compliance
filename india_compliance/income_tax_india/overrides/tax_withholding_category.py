import frappe


def on_change(doc, method=None):
    frappe.cache.delete_value("tax_withholding_accounts")


def get_tax_withholding_accounts(company):
    def _get_tax_withholding_accounts():
        return set(frappe.get_all("Tax Withholding Account", pluck="account", filters={"company": company}))

    return frappe.cache.hget("tax_withholding_accounts", company, generator=_get_tax_withholding_accounts)


def get_tax_id_for_party(party_type, party):
    # PAN field is only available for Customer and Supplier.
    if party_type in ("Customer", "Supplier"):
        return frappe.db.get_value(party_type, party, "pan")

    return ""
