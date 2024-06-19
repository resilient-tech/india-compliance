import frappe
from frappe.query_builder import Case

from india_compliance.gst_india.constants import GST_ACCOUNT_FIELDS

doctype_tax_map = {
    "Bill of Entry": "Bill of Entry Taxes",
    "Payment Entry": "Advance Taxes and Charges",
    "Supplier Quotation": "Purchase Taxes and Charges",
    "Purchase Order": "Purchase Taxes and Charges",
    "Purchase Receipt": "Purchase Taxes and Charges",
    "Purchase Invoice": "Purchase Taxes and Charges",
    "Quotation": "Sales Taxes and Charges",
    "Sales Order": "Sales Taxes and Charges",
    "Delivery Note": "Sales Taxes and Charges",
    "Sales Invoice": "Sales Taxes and Charges",
    "POS Invoice": "Sales Taxes and Charges",
}


def execute():
    gst_accounts = frappe.get_doc("GST Settings").gst_accounts
    gst_details = {}

    for row in gst_accounts:
        for account in GST_ACCOUNT_FIELDS:
            account_value = row.get(account)

            if not account_value:
                continue

            if row.get("account_type") == "Reverse Charge":
                gst_details.setdefault(account[:-8] + "_rcm", []).append(account_value)

            elif row.get("account_type") != "Reverse Charge":
                gst_details.setdefault(account[:-8], []).append(account_value)

    for doctype, tax_doctype in doctype_tax_map.items():
        update_documents(doctype, tax_doctype, gst_details)


def update_documents(doctype, child_doctype, gst_accounts):
    parent_doctype = frappe.qb.DocType(doctype, alias="parent_doctype")
    child_doctype = frappe.qb.DocType(child_doctype, alias="child_doctype")

    update_query = (
        frappe.qb.update(child_doctype)
        .join(parent_doctype)
        .on(child_doctype.parent == parent_doctype.name)
    )
    conditions = Case()

    for gst_tax_account, gst_tax_name in gst_accounts.items():
        conditions = conditions.when(
            child_doctype.account_head.isin(gst_tax_name), gst_tax_account
        )

    update_query = update_query.set(child_doctype.gst_tax_type, conditions).run(
        as_dict=True
    )
