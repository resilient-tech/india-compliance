import frappe
from frappe.query_builder import Case

from india_compliance.gst_india.constants import GST_ACCOUNT_FIELDS

doctype_tax_map = {
    "Bill of Entry": "Bill of Entry Taxes",
    "Payment Entry": "Advance Taxes and Charges",
    "Purchase Invoice": "Purchase Taxes and Charges",
    "Sales Invoice": "Sales Taxes and Charges",
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
                gst_details.setdefault(account + "_rcm", []).append(account_value)

            elif row.get("account_type") != "Reverse Charge":
                gst_details.setdefault(account, []).append(account_value)

    for doctype, tax_doctype in doctype_tax_map.items():
        update_documents(doctype, tax_doctype, gst_details)


def update_documents(doctype, child_doctype, gst_accounts):
    parent_doctype = frappe.qb.DocType(doctype, alias="parent_doctype")
    child_doctype = frappe.qb.DocType(child_doctype, alias="child_doctype")

    (
        frappe.qb.update(child_doctype)
        .join(parent_doctype)
        .on(child_doctype.parent == parent_doctype.name)
        .set(
            child_doctype.gst_tax_type,
            Case()
            .when(
                child_doctype.account_head.isin(
                    gst_accounts.get("igst_account") or [""]
                ),
                "igst",
            )
            .when(
                child_doctype.account_head.isin(
                    gst_accounts.get("cgst_account") or [""]
                ),
                "cgst",
            )
            .when(
                child_doctype.account_head.isin(
                    gst_accounts.get("sgst_account") or [""]
                ),
                "sgst",
            )
            .when(
                child_doctype.account_head.isin(
                    gst_accounts.get("cess_account") or [""]
                ),
                "cess",
            )
            .when(
                child_doctype.account_head.isin(
                    gst_accounts.get("cess_non_advol_account") or [""]
                ),
                "cess_non_advol",
            )
            .when(
                child_doctype.account_head.isin(
                    gst_accounts.get("igst_account_rcm") or [""]
                ),
                "igst_rcm",
            )
            .when(
                child_doctype.account_head.isin(
                    gst_accounts.get("cgst_account_rcm") or [""]
                ),
                "cgst_rcm",
            )
            .when(
                child_doctype.account_head.isin(
                    gst_accounts.get("sgst_account_rcm") or [""]
                ),
                "sgst_rcm",
            )
            .when(
                child_doctype.account_head.isin(
                    gst_accounts.get("cess_account_rcm") or [""]
                ),
                "cess_rcm",
            )
            .when(
                child_doctype.account_head.isin(
                    gst_accounts.get("cess_non_advol_account_rcm") or [""]
                ),
                "cess_non_advol_rcm",
            )
            .else_(""),
        )
    ).run(as_dict=True)
