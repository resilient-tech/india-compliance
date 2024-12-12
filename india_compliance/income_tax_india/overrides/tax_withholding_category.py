import frappe


def on_change(doc, method=None):
<<<<<<< HEAD
    frappe.cache().delete_value("tax_withholding_accounts")
=======
    frappe.cache.delete_value("tax_withholding_accounts")
>>>>>>> 159ed757 (test: additionally test gst details for credit note with zero value)


def get_tax_withholding_accounts(company):
    def _get_tax_withholding_accounts():
        return set(
            frappe.get_all(
                "Tax Withholding Account", pluck="account", filters={"company": company}
            )
        )

<<<<<<< HEAD
    return frappe.cache().hget(
=======
    return frappe.cache.hget(
>>>>>>> 159ed757 (test: additionally test gst details for credit note with zero value)
        "tax_withholding_accounts", company, generator=_get_tax_withholding_accounts
    )
