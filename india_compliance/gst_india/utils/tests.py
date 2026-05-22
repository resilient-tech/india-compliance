import frappe
from erpnext.controllers.subcontracting_controller import make_rm_stock_entry
from frappe.utils import getdate

from india_compliance.gst_india.constants import SALES_DOCTYPES
from india_compliance.gst_india.utils import get_gst_accounts_by_type
from india_compliance.tests.erpnext_test_utils import create_subcontracting_order

SUBCONTRACTING_TEST_RM_ITEM_1 = "Subcontracted SRM Item 1"
SUBCONTRACTING_TEST_RM_ITEM_2 = "Subcontracted SRM Item 2"
SUBCONTRACTING_TEST_SERVICE_ITEM = "Subcontracted Service Item 1"
SUBCONTRACTING_TEST_FINISHED_ITEM = "Subcontracted Item SA1"
SUBCONTRACTING_TEST_FINISHED_ITEM_2 = "Subcontracted Item SA2"


def create_sales_invoice(**data):
    data["doctype"] = "Sales Invoice"
    return create_transaction(**data)


def create_purchase_invoice(**data):
    data["doctype"] = "Purchase Invoice"

    if "bill_no" not in data:
        data["bill_no"] = frappe.generate_hash(length=5)

    return create_transaction(**data)


def create_journal_entry(**data):
    data = frappe._dict(data)
    data["doctype"] = "Journal Entry"

    return create_transaction(**data)


def create_itc_reversal_journal_entry(**data):
    """
    Create an ITC Reversal Journal Entry.
    """
    data = frappe._dict(data)
    if not data.get("voucher_type"):
        data["voucher_type"] = "Reversal Of ITC"

    if not data.get("ineligibility_reason"):
        data["ineligibility_reason"] = "As per rules 42 & 43 of CGST Rules"

    if not data.get("accounts") and data.get("tax_amount"):
        data["accounts"] = get_itc_journal_accounts(data)

    data.pop("tax_amount", None)

    return create_journal_entry(**data)


def create_itc_reclaim_journal_entry(**data):
    """
    Create an ITC Reclaim Journal Entry.
    """
    data = frappe._dict(data)
    if not data.get("voucher_type"):
        data["voucher_type"] = "Reclaim of ITC Reversal"

    if not data.get("accounts") and data.get("tax_amount"):
        data["accounts"] = get_itc_journal_accounts(data)

    data.pop("tax_amount", None)

    return create_journal_entry(**data)


def get_itc_journal_accounts(data):
    tax_amount = data.tax_amount
    company = data.company or "_Test Indian Registered Company"
    company_abbr = frappe.get_cached_value("Company", company, "abbr")
    is_reclaim = data.get("voucher_type") == "Reclaim of ITC Reversal"
    gst_accounts = get_gst_accounts_by_type(company, "Input")

    return [
        {
            "account": f"GST Expense - {company_abbr}",
            "credit_in_account_currency" if is_reclaim else "debit_in_account_currency": tax_amount * 2,
        },
        {
            "account": gst_accounts.cgst_account,
            "debit_in_account_currency" if is_reclaim else "credit_in_account_currency": tax_amount,
        },
        {
            "account": gst_accounts.sgst_account,
            "debit_in_account_currency" if is_reclaim else "credit_in_account_currency": tax_amount,
        },
    ]


def create_transaction(**data):
    data = frappe._dict(data)
    transaction = frappe.get_doc(data)

    if not transaction.company:
        transaction.company = "_Test Indian Registered Company"

    # Update mandatory transaction dates
    if transaction.doctype in [
        "Purchase Order",
        "Quotation",
        "Sales Order",
        "Supplier Quotation",
    ]:
        if not transaction.transaction_date:
            transaction.transaction_date = getdate()

        if transaction.doctype == "Sales Order":
            transaction.delivery_date = getdate()

        if transaction.doctype == "Purchase Order":
            transaction.schedule_date = getdate()

    elif not transaction.posting_date:
        transaction.posting_date = getdate()

    if transaction.doctype in SALES_DOCTYPES:
        if not transaction.get("customer") and transaction.doctype != "Quotation":
            transaction.customer = "_Test Registered Customer"

    elif transaction.doctype not in ["Payment Entry", "Journal Entry"]:
        if not transaction.supplier:
            transaction.supplier = "_Test Registered Supplier"

    if transaction.doctype == "POS Invoice":
        transaction.append(
            "payments",
            {
                "mode_of_payment": "Cash",
            },
        )

    company_abbr = frappe.get_cached_value("Company", data.company, "abbr") or "_TIRC"

    if not data.get("items"):
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


def make_subcontracting_stock_entry(**data):
    data = frappe._dict(data)
    do_not_save = data.pop("do_not_save", False)
    do_not_submit = data.pop("do_not_submit", False)
    data.pop("items", None)  # always derived from SCO supplied_items

    purchase_order = create_transaction(
        doctype="Purchase Order",
        is_subcontracted=1,
        item_code=SUBCONTRACTING_TEST_SERVICE_ITEM,
        qty=1,
        rate=100,
        fg_item=SUBCONTRACTING_TEST_FINISHED_ITEM,
        fg_item_qty=1,
        supplier_warehouse="Finished Goods - _TIRC",
    )
    subcontracting_order = create_subcontracting_order(po_name=purchase_order.name)

    items = [
        {
            "item_code": row.main_item_code,
            "rm_item_code": row.rm_item_code,
            "qty": row.required_qty,
            "rate": row.rate,
            "stock_uom": row.stock_uom,
            "warehouse": row.reserve_warehouse,
        }
        for row in subcontracting_order.supplied_items
    ]

    stock_entry = frappe.get_doc(make_rm_stock_entry(subcontracting_order.name, items))
    stock_entry.update(data)

    if "bill_from_address" not in data and not stock_entry.get("bill_from_address"):
        stock_entry.bill_from_address = "_Test Indian Registered Company-Billing"

    if "bill_to_address" not in data and not stock_entry.get("bill_to_address"):
        stock_entry.bill_to_address = "_Test Registered Supplier-Billing"

    if do_not_save:
        return stock_entry

    stock_entry.insert()

    if do_not_submit:
        return stock_entry

    return stock_entry.submit()


def append_item(transaction, data=None, company_abbr="_TIRC"):
    if not data:
        data = frappe._dict()

    if data.doctype in ["Payment Entry", "Journal Entry"]:
        return

    return transaction.append(
        "items",
        {
            "item_code": data.item_code or "_Test Trading Goods 1",
            "qty": data.qty or 1,
            "uom": data.uom,
            "rate": data.rate or 100,
            "cost_center": f"Main - {company_abbr}",
            "item_tax_template": data.item_tax_template,
            "gst_treatment": data.gst_treatment,
            "gst_hsn_code": data.gst_hsn_code,
            "warehouse": f"Stores - {company_abbr}",
            "expense_account": f"Cost of Goods Sold - {company_abbr}",
            "taxable_value": data.taxable_value or 0,
            "fg_item": data.fg_item,
            "fg_item_qty": data.fg_item_qty,
        },
    )


def _append_taxes(
    transaction,
    accounts,
    company_abbr="_TIRC",
    rate=9,
    charge_type="On Net Total",
    row_id=None,
    tax_amount=None,
    **kwargs,
):
    if isinstance(accounts, str):
        accounts = [accounts]

    if transaction.doctype in SALES_DOCTYPES or transaction.doctype == "Payment Entry":
        account_type = "Output Tax"
    else:
        account_type = "Input Tax"

    if transaction.doctype == "Payment Entry" and charge_type == "On Net Total":
        charge_type = "On Paid Amount"

    for account in accounts:
        tax = {
            "charge_type": charge_type,
            "row_id": row_id,
            "account_head": f"{account_type} {account} - {company_abbr}",
            "description": account,
            "rate": rate,
            "cost_center": f"Main - {company_abbr}",
            **kwargs,
        }

        if tax_amount:
            tax["tax_amount"] = tax_amount

        if account.endswith("RCM"):
            if transaction.doctype in SALES_DOCTYPES:
                tax["rate"] = -tax["rate"]
            else:
                tax["add_deduct_tax"] = "Deduct"

        transaction.append("taxes", tax)
