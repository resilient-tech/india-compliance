import re

import frappe
from frappe import _

from india_compliance.gst_india.utils import (
    get_all_gst_accounts,
    get_gst_accounts_by_type,
)

# Maximum length must be 16 characters. First character must be alphanumeric.
# Subsequent characters can be alphanumeric, hyphens or slashes.
GST_INVOICE_NUMBER_FORMAT = re.compile(r"^[^\W_][A-Za-z0-9\-\/]{0,15}$")


def validate_gst_invoice(doc, method=None):
    country, gst_category = frappe.get_cached_value(
        "Company", doc.company, ("country", "gst_category")
    )
    if country != "India" or gst_category == "Unregistered":
        return

    validate_invoice_number(doc)
    validate_mandatory_fields(doc)
    validate_item_tax_template(doc)
    validate_gst_accounts(doc)


def validate_invoice_number(doc):
    """Validate GST invoice number requirements."""

    if not GST_INVOICE_NUMBER_FORMAT.match(doc.name):
        frappe.throw(
            _(
                "Invoice Number should only contain alphanumeric values, dash(-) and"
                " slash(/) and cannot exceed 16 digits."
            ),
            title=_("Invalid GST Invoice Number"),
        )


def validate_mandatory_fields(doc):
    fields = ["company_gstin", "place_of_supply"]

    for field in fields:
        if not doc.get(field):
            frappe.throw(
                _("{0} is a mandatory field for compliant GST Invoice.").format(
                    _(doc.meta.get_label(field))
                )
            )


def validate_item_tax_template(doc):
    """
    Different item tax templates should not be used for same item-code in one document.
    """

    if not doc.has_value_changed("grand_total") or not frappe.db.get_single_value(
        "Selling Settings", "allow_multiple_items"
    ):
        return

    item_tax_template = frappe._dict()
    items_with_duplicate_taxes = []
    for item in doc.items or []:
        if (
            item.item_code in item_tax_template
            and item.get("item_tax_template", "") != item_tax_template[item.item_code]
        ):
            items_with_duplicate_taxes.append(item.item_code)
        item_tax_template[item.item_code] = item.get("item_tax_template", "")

    if items_with_duplicate_taxes:
        frappe.throw(
            _("You have used different Item-tax Templates for items {0}.").format(
                "\n".join(items_with_duplicate_taxes)
            ),
            title="Invalid Item-tax Template",
        )


def validate_gst_accounts(doc):
    """
    Validate GST accounts before invoice creation
    - Only Output Accounts should be allowed in GST Sales Invoice
    - If supply made to SEZ/Overseas without payment of tax, then no GST account should be specified
    - SEZ supplies should not have CGST or SGST account
    - Inter-State supplies should not have CGST or SGST account
    - Intra-State supplies should not have IGST account
    """

    accounts_list = get_all_gst_accounts(doc.company)
    output_accounts = get_gst_accounts_by_type(doc.company, "Output")
    no_tax = (
        doc.gst_category in ["SEZ", "Overseas"]
        and doc.export_type == "Without Payment of Tax"
    )
    inter_state = (
        doc.place_of_supply[:2] != doc.company_gstin[:2] or doc.gst_category == "SEZ"
    )

    for row in doc.taxes or []:
        account_head = row.account_head
        tax_amount = row.tax_amount
        if account_head not in accounts_list:
            continue

        if (
            account_head not in (output_account_values := output_accounts.values())
            and tax_amount
        ):
            frappe.throw(
                _(
                    "{0} is not an Output Account. Only output accounts should be"
                    " selected in Sales Transactions."
                ).format(account_head)
            )

        if no_tax:
            if account_head in output_account_values and tax_amount:
                frappe.throw(
                    _(
                        "{0} should not have any tax amount as you are making supply"
                        " without payment of tax."
                    ).format(account_head)
                )
        elif inter_state:
            if (
                account_head
                in (output_accounts.cgst_account, output_accounts.sgst_account)
                and tax_amount
            ):
                frappe.throw(
                    _(
                        "{0} should to be IGST Account as you are making inter-state"
                        " supply."
                    ).format(account_head)
                )
        else:
            if account_head == output_accounts.igst_account and tax_amount:
                frappe.throw(
                    _(
                        "{0} should to be CGST/SGST Account as you are making"
                        " intra-state supply."
                    ).format(account_head)
                )
