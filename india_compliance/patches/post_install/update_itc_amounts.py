import frappe

from india_compliance.gst_india.utils import GST_ACCOUNT_FIELDS


def execute():
    if "eligibility_for_itc" not in frappe.db.get_table_columns("Purchase Invoice"):
        return

    itc_amounts = {
        "itc_integrated_tax": 0,
        "itc_state_tax": 0,
        "itc_central_tax": 0,
        "itc_cess_amount": 0,
    }

    for field in itc_amounts:
        frappe.db.sql(
            f"""
            UPDATE `tabPurchase Invoice`
            SET {field} = 0
            WHERE trim(coalesce({field}, '')) = ''
            """
        )

    gst_accounts = get_gst_accounts(only_non_reverse_charge=1)

    if not gst_accounts:
        return

    # Get purchase invoices where ITC amounts are not set
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
        where parent in %s
        GROUP BY parent, account_head
    """,
        (invoice_list,),
        as_dict=1,
    )

    if not gst_tax_amounts:
        return

    account_types = ["igst_account", "sgst_account", "cgst_account", "cess_account"]
    account_amount_fields = dict(zip(account_types, itc_amounts.keys()))
    itc_amounts_to_update = {}

    # Get ITC amounts to update for each Invoice
    for row in gst_tax_amounts:
        amount_field = next(
            (
                amount_field
                for account_type, amount_field in account_amount_fields.items()
                if row.account_head in (gst_accounts.get(account_type) or ())
            ),
            None,
        )

        if not amount_field:
            continue

        itc_amounts = itc_amounts_to_update.setdefault(row.parent, itc_amounts.copy())
        itc_amounts[amount_field] += row.amount

    # Update ITC amounts
    update_count = 0

    for invoice, values in itc_amounts_to_update.items():
        frappe.db.set_value("Purchase Invoice", invoice, values)
        update_count += 1

        if update_count % 1000 == 0:
            frappe.db.commit()


def get_gst_accounts(
    company=None,
    account_wise=False,
    only_reverse_charge=0,
    only_non_reverse_charge=0,
):
    filters = {}

    if company:
        filters["company"] = company
    if only_reverse_charge:
        filters["account_type"] = "Reverse Charge"
    elif only_non_reverse_charge:
        filters["account_type"] = ("!=", "Reverse Charge")

    settings = frappe.get_cached_doc("GST Settings", "GST Settings")
    gst_accounts = settings.get("gst_accounts", filters)
    result = frappe._dict()

    for row in gst_accounts:
        for fieldname in GST_ACCOUNT_FIELDS:
            if not (value := row.get(fieldname)):
                continue

            if not account_wise:
                result.setdefault(fieldname, []).append(value)
            else:
                result[value] = fieldname

    return result
