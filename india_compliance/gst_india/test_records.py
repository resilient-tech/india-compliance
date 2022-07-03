import frappe
from frappe.utils import nowdate, sbool


def create_sales_invoice(**args):
    abbr = frappe.get_cached_value("Company", args.company, "abbr") or "_TIRC"
    si = frappe.new_doc("Sales Invoice")
    args = frappe._dict(args)

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

    if args.is_in_state:
        append_taxes(si, ["CGST", "SGST"], abbr, True)
    elif args.is_in_state is False:
        append_taxes(si, "IGST", abbr, True, 18)

    if not args.do_not_save:
        si.insert()
        if not args.do_not_submit:
            si.submit()

    return si


def create_purchase_invoice(**args):
    abbr = frappe.get_cached_value("Company", args.company, "abbr") or "_TIRC"
    pi = frappe.new_doc("Purchase Invoice")
    args = frappe._dict(args)

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

    if args.is_in_state or args.is_in_state_rcm:
        append_taxes(pi, ["CGST", "SGST"], abbr)
    elif args.is_in_state is False or args.is_in_state_rcm is False:
        append_taxes(pi, "IGST", abbr, rate=18)

    if args.is_in_state_rcm:
        append_taxes(pi, ["CGST RCM", "SGST RCM"], abbr)
    elif args.is_in_state_rcm is False:
        append_taxes(pi, "IGST RCM", abbr, rate=18)

    if not args.do_not_save:
        pi.insert()
        if not args.do_not_submit:
            pi.submit()

    return pi


def append_taxes(obj, accounts, abbr, is_sales=False, rate=9):

    if isinstance(accounts, str):
        accounts = [accounts]

    if is_sales:
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


def append_items(obj, args, abbr):
    obj.append(
        "items",
        {
            "item_code": args.item_code or "_Test Trading Goods 1",
            "qty": args.qty or 5,
            "rate": args.rate or 50,
            "cost_center": f"Main - {abbr}",
        },
    )
