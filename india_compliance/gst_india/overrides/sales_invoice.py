import re

import frappe
from frappe import _, bold

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

    if len(doc.name > 16):
        frappe.throw(
            _("GST Invoice Number cannot exceed 16 characters"),
            title=_("Invalid GST Invoice Number"),
        )

    if not GST_INVOICE_NUMBER_FORMAT.match(doc.name):
        frappe.throw(
            _(
                "GST Invoice Number should start with an alphanumeric character and can"
                " only contain alphanumeric characters, dash (-) and slash (/)"
            ),
            title=_("Invalid GST Invoice Number"),
        )


def validate_mandatory_fields(doc):
    for field in ("company_gstin", "place_of_supply"):
        if not doc.get(field):
            frappe.throw(
                _(
                    "{0} is a mandatory field for creating a GST Compliant Invoice"
                ).format(
                    bold(_(doc.meta.get_label(field))),
                )
            )


def validate_item_tax_template(doc):
    """Different Item Tax Templates should not be used for the same Item Code"""

    if not doc.has_value_changed("grand_total") or not doc.items:
        return

    item_tax_templates = frappe._dict()
    items_with_duplicate_taxes = []

    for row in doc.items:
        if row.item_code not in item_tax_templates:
            item_tax_templates[row.item_code] = row.item_tax_template
            continue

        if row.item_tax_template != item_tax_templates[row.item_code]:
            items_with_duplicate_taxes.append(bold(row.item_code))

    if items_with_duplicate_taxes:
        frappe.throw(
            _(
                "Cannot use different Item Tax Templates in different rows for"
                " following items:<br> {0}"
            ).format("<br>".join(items_with_duplicate_taxes)),
            title="Inconsistent Item Tax Templates",
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

    if not doc.taxes:
        return

    accounts_list = get_all_gst_accounts(doc.company)
    output_accounts = get_gst_accounts_by_type(doc.company, "Output")

    for row in doc.taxes:
        account_head = row.account_head

        if account_head not in accounts_list or not row.tax_amount:
            continue

        if (
            doc.gst_category in ("SEZ", "Overseas")
            and doc.export_type == "Without Payment of Tax"
        ):
            frappe.throw(
                _(
                    "Cannot charge GST in Row #{0} since Export Type is set to Without"
                    " Payment of Tax"
                ).format(row.idx)
            )

        if account_head not in output_accounts.values():
            frappe.throw(
                _(
                    "{0} is not an Output GST Account and cannot be used in Sales"
                    " Transactions."
                ).format(bold(account_head))
            )

        # Inter State supplies should not have CGST or SGST account
        if (
            doc.place_of_supply[:2] != doc.company_gstin[:2]
            or doc.gst_category == "SEZ"
        ):
            if account_head in (
                output_accounts.cgst_account,
                output_accounts.sgst_account,
            ):
                frappe.throw(
                    _(
                        "Row #{0}: Cannot charge CGST/SGST for inter-state supplies"
                    ).format(row.idx)
                )

        # Intra State supplies should not have IGST account
        elif account_head == output_accounts.igst_account:
            frappe.throw(
                _("Row #{0}: Cannot charge IGST for intra-state supplies").format(
                    row.idx
                )
            )
