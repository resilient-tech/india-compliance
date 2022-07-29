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
    validate_bill_no(doc)


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


def validate_bill_no(doc):
    if (
        not doc.supplier_gstin
        or doc.bill_no
        or not frappe.get_cached_value(
            "GST Settings", "GST Settings", "validate_bill_no"
        )
    ):
        return

    gst_accounts = get_gst_accounts_by_type(doc.company, "Input").values()
    for tax in doc.get("taxes"):
        if (
            tax.account_head not in gst_accounts
            or not tax.base_tax_amount_after_discount_amount
        ):
            continue

        frappe.throw(
            _(
                "Bill No is mandatory for a GST Purchase Invoice from a Registered Supplier."
            ),
            title=_("Missing Mandatory Field"),
        )
