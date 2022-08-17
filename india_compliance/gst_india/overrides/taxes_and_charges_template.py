import frappe
from frappe import _

from india_compliance.gst_india.overrides.transaction import (
    get_valid_accounts,
    is_indian_registered_company,
)
from india_compliance.gst_india.utils import (
    get_all_gst_accounts,
    get_gst_accounts_by_type,
)


def validate(doc, method=None):
    if not is_indian_registered_company(doc):
        return

    validate_gst_accounts(doc)


def validate_gst_accounts(doc):
    if not (
        rows_to_validate := [
            row
            for row in doc.taxes
            if row.account_head in get_all_gst_accounts(doc.company)
        ]
    ):
        return

    for_sales = doc.doctype == "Sales Taxes and Charges Template"
    all_valid_accounts, intra_state_accounts, inter_state_accounts = get_valid_accounts(
        doc.company, for_sales
    )
    reverse_charge_accounts = get_gst_accounts_by_type(
        doc.company, "Reverse Charge"
    ).values()

    for row in rows_to_validate:
        if doc.is_inter_state:
            if row.account_head not in inter_state_accounts:
                frappe.throw(
                    _(
                        "GST Account at row #{0} is not a valid account for {1} for inter state transactions"
                    ).format(frappe.bold(row.idx), frappe.bold(doc.doctype))
                )

        else:
            if row.account_head not in intra_state_accounts:
                frappe.throw(
                    _(
                        "GST Account at row #{0} is not a valid account for {1} for intra state transactions"
                    ).format(frappe.bold(row.idx), frappe.bold(doc.doctype))
                )

        if for_sales or doc.is_reverse_charge:
            continue

        if row.account_head in reverse_charge_accounts:
            frappe.throw(
                _(
                    "Reverse Charge Account at row #{0} cannot be used for tax template without reverse charge"
                ).format(frappe.bold(row.idx))
            )
