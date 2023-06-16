import frappe
from frappe.utils import flt

from india_compliance.gst_india.overrides.transaction import validate_transaction
from india_compliance.gst_india.utils import get_gst_accounts_by_type


def validate(doc, method=None):
    if validate_transaction(doc) is False:
        return

    update_itc_totals(doc)


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


def onload(doc, method):
    if doc.docstatus != 1 or doc.gst_category != "Overseas":
        return

    doc.set_onload(
        "bill_of_entry_exists",
        frappe.db.exists(
            "Bill of Entry",
            {"purchase_invoice": doc.name, "docstatus": 1},
        ),
    )


def get_dashboard_data(data):
    transactions = data.setdefault("transactions", [])
    reference_section = next(
        (row for row in transactions if row.get("label") == "Reference"), None
    )

    if reference_section is None:
        reference_section = {"label": "Reference", "items": []}
        transactions.append(reference_section)

    reference_section["items"].append("Bill of Entry")

    return data
