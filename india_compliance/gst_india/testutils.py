import frappe
from frappe.utils import nowdate, sbool

from india_compliance.gst_india.constants import SALES_DOCTYPES


def create_sales_invoice(**args):
    args = frappe._dict(args)
    abbr = frappe.get_cached_value("Company", args.company, "abbr") or "_TIRC"
    si = frappe.new_doc("Sales Invoice")

    si.update(
        {
            "company": args.company or "_Test Indian Registered Company",
            "customer": args.customer or "_Test Registered Customer",
            "set_posting_time": sbool(args.set_posting_time),
            "posting_date": args.posting_date or nowdate(),
            "is_return": args.is_return,
            "is_reverse_charge": args.is_reverse_charge,
            "is_export_with_gst": args.is_export_with_gst,
        }
    )

    if args.customer_address:
        si.customer_address = args.customer_address

    append_items(si, args, abbr)
    append_taxes(si, args, abbr)

    if not args.do_not_save:
        si.insert()
        if not args.do_not_submit:
            si.submit()

    return si


def create_purchase_invoice(**args):
    args = frappe._dict(args)
    abbr = frappe.get_cached_value("Company", args.company, "abbr") or "_TIRC"
    pi = frappe.new_doc("Purchase Invoice")

    pi.update(
        {
            "company": args.company or "_Test Indian Registered Company",
            "supplier": args.supplier or "_Test Registered Supplier",
            "set_posting_time": sbool(args.set_posting_time),
            "posting_date": args.posting_date or nowdate(),
            "is_return": args.is_return,
            "is_reverse_charge": args.is_reverse_charge,
            "eligible_for_itc": args.eligible_for_itc or "All Other ITC",
        }
    )

    append_items(pi, args, abbr)
    append_taxes(pi, args, abbr)

    if not args.do_not_save:
        pi.insert()
        if not args.do_not_submit:
            pi.submit()

    return pi


def append_items(obj, args, abbr="_TIRC"):
    obj.append(
        "items",
        {
            "item_code": args.item_code or "_Test Trading Goods 1",
            "qty": args.qty or 1,
            "rate": args.rate or 100,
            "cost_center": f"Main - {abbr}",
            "is_nil_exempt": args.is_nil_exempt,
            "is_non_gst": args.is_non_gst,
            "item_tax_template": args.item_tax_template,
        },
    )


def append_taxes(obj, args, abbr="_TIRC"):
    if args.is_in_state or args.is_in_state_rcm:
        _append_taxes(obj, ["CGST", "SGST"], abbr)
    elif args.is_out_state or args.is_out_state_rcm:
        _append_taxes(obj, "IGST", abbr, rate=18)

    if args.is_in_state_rcm:
        _append_taxes(obj, ["CGST RCM", "SGST RCM"], abbr)
    elif args.is_out_state_rcm:
        _append_taxes(obj, "IGST RCM", abbr, rate=18)


def _append_taxes(obj, accounts, abbr="_TIRC", rate=9):

    if isinstance(accounts, str):
        accounts = [accounts]

    if obj.doctype in SALES_DOCTYPES:
        account_type = "Output Tax"
    else:
        account_type = "Input Tax"

    for account in accounts:
        taxes = {
            "charge_type": "On Net Total",
            "account_head": f"{account_type} {account} - {abbr}",
            "description": f"{account}",
            "rate": rate,
            "cost_center": f"Main - {abbr}",
        }

        if account.endswith("RCM"):
            taxes["add_deduct_tax"] = "Deduct"

        obj.append("taxes", taxes)
