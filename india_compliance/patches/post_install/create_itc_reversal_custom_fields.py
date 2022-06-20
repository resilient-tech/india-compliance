import frappe

from india_compliance.gst_india.utils import get_gst_accounts_by_type


def execute():
    itc_amounts = {
        "itc_integrated_tax": 0,
        "itc_state_tax": 0,
        "itc_central_tax": 0,
        "itc_cess_amount": 0,
    }

    for field in itc_amounts:
        frappe.db.sql(
            """UPDATE `tabPurchase Invoice` set {field} = '0'
            WHERE trim(coalesce({field}, '')) = '' """.format(
                field=field
            )
        )

    gst_accounts = get_gst_accounts_for_all_companies()

    if not gst_accounts:
        return

    # Get purchase invoices where ITC is not zero
    invoice_list = frappe.get_all(
        "Purchase Invoice",
        {
            "docstatus": 1,
            "posting_date": (">=", "2021-04-01"),
            "eligibility_for_itc": ("!=", "Ineligible"),
            **itc_amounts,
        },
        pluck="name",
    )

    if not invoice_list:
        return

    # Get GST applied
    gst_tax_amounts = frappe.db.sql(
        """
        SELECT parent, account_head, sum(base_tax_amount_after_discount_amount) as amount
        FROM `tabPurchase Taxes and Charges`
        where parent in %s and
        account_head in %s
        GROUP BY parent, account_head
    """,
        (invoice_list, list(gst_accounts.keys())),
        as_dict=1,
    )

    if not gst_tax_amounts:
        return

    accounts = ["igst_account", "sgst_account", "cgst_account", "cess_account"]
    accounts_map = dict(zip(accounts, itc_amounts.keys()))
    itc_amounts_to_update = {}

    # Get ITC amounts to update for each Invoice
    for d in gst_tax_amounts:
        itc_amounts_to_update.setdefault(d.parent, itc_amounts.copy())

        if d.account_head in gst_accounts:
            field = accounts_map[gst_accounts[d.account_head]]
            itc_amounts_to_update[d.parent][field] += d.amount

    # Update ITC amounts
    for invoice, values in itc_amounts_to_update.items():
        frappe.db.set_value("Purchase Invoice", invoice, values)


def get_gst_accounts_for_all_companies():
    gst_accounts = dict()
    company_list = frappe.get_all("Company", filters={"country": "India"}, pluck="name")

    for company in company_list:
        company_accounts = get_gst_accounts_by_type(company, "Input", throw=False)
        gst_accounts.update({v: k for k, v in company_accounts.items() if v})

    return gst_accounts
