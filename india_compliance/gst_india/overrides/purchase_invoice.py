import frappe
from frappe import _
from frappe.utils import flt

from india_compliance.gst_india.overrides.transaction import validate_transaction
from india_compliance.gst_india.utils import get_gst_accounts_by_type


def validate(doc, method=None):
    if validate_transaction(doc) is False:
        return

    update_itc_totals(doc)
    validate_supplier_gstin(doc)
    validate_with_inward_supply(doc)


def update_itc_totals(doc, method=None):
    # Initialize values
    doc.itc_integrated_tax = 0
    doc.itc_state_tax = 0
    doc.itc_central_tax = 0
    doc.itc_cess_amount = 0

    gst_accounts = get_gst_accounts_by_type(doc.company, "Input")

    for tax in doc.get("taxes"):
        if tax.account_head == gst_accounts.igst_account:
            doc.itc_integrated_tax += flt(tax.base_tax_amount_after_discount_amount)

        if tax.account_head == gst_accounts.sgst_account:
            doc.itc_state_tax += flt(tax.base_tax_amount_after_discount_amount)

        if tax.account_head == gst_accounts.cgst_account:
            doc.itc_central_tax += flt(tax.base_tax_amount_after_discount_amount)

        if tax.account_head == gst_accounts.cess_account:
            doc.itc_cess_amount += flt(tax.base_tax_amount_after_discount_amount)


def validate_supplier_gstin(doc):
    if doc.company_gstin == doc.supplier_gstin:
        frappe.throw(
            _("Supplier GSTIN and Company GSTIN cannot be the same"),
            title=_("Invalid Supplier GSTIN"),
        )


def validate_with_inward_supply(doc):
    if not doc.get("_inward_supply"):
        return

    mismatch_fields = {}
    for field in [
        "company",
        "company_gstin",
        "supplier_gstin",
        "bill_no",
        "bill_date",
        "is_reverse_charge",
        "place_of_supply",
    ]:
        if doc.get(field) != doc._inward_supply.get(field):
            mismatch_fields[field] = doc._inward_supply.get(field)

    # mismatch for taxable_value
    taxable_value = sum([item.taxable_value for item in doc.items])
    if taxable_value != doc._inward_supply.get("taxable_value"):
        mismatch_fields["Taxable Value"] = doc._inward_supply.get("taxable_value")

    # mismatch for taxes
    gst_accounts = get_gst_accounts_by_type(doc.company, "Input")
    for tax in ["cgst", "sgst", "igst", "cess"]:
        tax_amount = get_tax_amount(doc.taxes, gst_accounts[tax + "_account"])
        if tax == "cess":
            tax_amount += get_tax_amount(doc.taxes, gst_accounts.cess_non_advol_account)

        if tax_amount == doc._inward_supply.get(tax):
            continue

        mismatch_fields[tax.upper()] = doc._inward_supply.get(tax)

    if mismatch_fields:
        message = (
            "Purchase Invoice does not match with releted GST Inward Supply.<br>"
            "Following values are not matching from 2A/2B: <br>"
        )
        for field, value in mismatch_fields.items():
            message += f"<br>{field}: {value}"

        frappe.msgprint(
            _(message),
            title=_("Mismatch with GST Inward Supply"),
        )

    elif doc._action == "submit":
        frappe.msgprint(
            _("Invoice matched with GST Inward Supply"),
            alert=True,
            indicator="green",
        )


def get_tax_amount(taxes, account_head):
    if not (taxes or account_head):
        return 0

    return sum(
        [
            tax.base_tax_amount_after_discount_amount
            for tax in taxes
            if tax.account_head == account_head
        ]
    )
