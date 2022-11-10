import frappe
from frappe.utils import getdate

from india_compliance.gst_india.constants import SALES_DOCTYPES


def create_sales_invoice(**data):
    data["doctype"] = "Sales Invoice"
    return create_transaction(**data)


def create_purchase_invoice(**data):
    data["doctype"] = "Purchase Invoice"
    return create_transaction(**data)


def create_transaction(**data):
    data = frappe._dict(data)
    transaction = frappe.get_doc(data)

    if not transaction.company:
        transaction.company = "_Test Indian Registered Company"

    # Update mandatory transaction dates
    if transaction.doctype in ["Purchase Order", "Quotation", "Sales Order"]:
        if not transaction.transaction_date:
            transaction.transaction_date = getdate()

        if transaction.doctype == "Sales Order":
            transaction.delivery_date = getdate()

        if transaction.doctype == "Purchase Order":
            transaction.schedule_date = getdate()

    elif not transaction.posting_date:
        transaction.posting_date = getdate()

    if transaction.doctype in SALES_DOCTYPES:
        if not transaction.customer:
            transaction.customer = "_Test Registered Customer"

    else:
        if not transaction.supplier:
            transaction.supplier = "_Test Registered Supplier"

        if (
            transaction.doctype == "Purchase Invoice"
            and not transaction.eligibility_for_itc
        ):
            transaction.eligibility_for_itc = "All Other ITC"

    if transaction.doctype == "POS Invoice":
        transaction.append(
            "payments",
            {
                "mode_of_payment": "Cash",
            },
        )

    company_abbr = frappe.get_cached_value("Company", data.company, "abbr") or "_TIRC"
    append_item(transaction, data, company_abbr)

    # Append taxes
    if data.is_in_state or data.is_in_state_rcm:
        _append_taxes(transaction, ["CGST", "SGST"], company_abbr, rate=9)

    if data.is_out_state or data.is_out_state_rcm:
        _append_taxes(transaction, "IGST", company_abbr, rate=18)

    if data.is_in_state_rcm:
        _append_taxes(transaction, ["CGST RCM", "SGST RCM"], company_abbr, rate=9)

    if data.is_out_state_rcm:
        _append_taxes(transaction, "IGST RCM", company_abbr, rate=18)

    if not data.do_not_save:
        transaction.insert()

        if not data.do_not_submit:
            transaction.submit()

    return transaction


def append_item(transaction, data=None, company_abbr="_TIRC"):
    if not data:
        data = frappe._dict()

    return transaction.append(
        "items",
        {
            "item_code": data.item_code or "_Test Trading Goods 1",
            "qty": data.qty or 1,
            "uom": data.uom,
            "rate": data.rate or 100,
            "cost_center": f"Main - {company_abbr}",
            "is_nil_exempt": data.is_nil_exempt,
            "is_non_gst": data.is_non_gst,
            "item_tax_template": data.item_tax_template,
            "gst_hsn_code": data.gst_hsn_code,
            "warehouse": f"Stores - {company_abbr}",
            "expense_account": f"Cost of Goods Sold - {company_abbr}",
        },
    )


def _append_taxes(
    transaction,
    accounts,
    company_abbr="_TIRC",
    rate=9,
    charge_type="On Net Total",
    row_id=None,
):
    if isinstance(accounts, str):
        accounts = [accounts]

    if transaction.doctype in SALES_DOCTYPES:
        account_type = "Output Tax"
    else:
        account_type = "Input Tax"

    for account in accounts:
        tax = {
            "charge_type": charge_type,
            "row_id": row_id,
            "account_head": f"{account_type} {account} - {company_abbr}",
            "description": account,
            "rate": rate,
            "cost_center": f"Main - {company_abbr}",
        }

        if account.endswith("RCM"):
            tax["add_deduct_tax"] = "Deduct"

        transaction.append("taxes", tax)
