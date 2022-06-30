import os

import frappe
from frappe.desk.page.setup_wizard.setup_wizard import setup_complete
from frappe.test_runner import make_test_objects
from frappe.utils import now_datetime, nowdate
from frappe.utils.nestedset import get_root_of
from erpnext.accounts.utils import get_fiscal_year


def before_tests():
    frappe.clear_cache()

    if not frappe.db.a_row_exists("Company"):
        now = now_datetime()
        year = now.year if now.month > 3 else now.year - 1

        setup_complete(
            {
                "currency": "INR",
                "full_name": "Test User",
                "company_name": "_Test Indian Registered Company",
                "timezone": "Asia/Kolkata",
                "company_abbr": "_TIRC",
                "industry": "Manufacturing",
                "country": "India",
                "fy_start_date": f"{year}-04-01",
                "fy_end_date": f"{year+1}-03-31",
                "language": "english",
                "company_tagline": "Testing",
                "email": "test@erpnext.com",
                "password": "test",
                "chart_of_accounts": "Standard",
            }
        )

    set_default_settings_for_tests()
    create_test_records()
    frappe.db.commit()


def set_default_settings_for_tests():
    for key in ("Customer Group", "Supplier Group", "Item Group", "Territory"):
        frappe.db.set_default(frappe.scrub(key), get_root_of(key))

    frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)


def create_test_records():
    test_records = read_json("test_records")

    for doctype, data in test_records.items():
        make_test_objects(doctype, data, reset=True)
        if doctype != "Company":
            continue

        setup_company_defaults(data)


def setup_company_defaults(data):
    add_company_to_fy(data)


def add_company_to_fy(data):
    fy = get_fiscal_year(now_datetime(), as_dict=True)
    doc = frappe.get_doc("Fiscal Year", fy.name)
    fy_companies = [row.company for row in doc.companies]

    for company in data:
        if company["company_name"] not in fy_companies:
            doc.append("companies", {"company": company["company_name"]})

    doc.save(ignore_permissions=True)


def read_json(name):
    file_path = os.path.join(os.path.dirname(__file__), "{name}.json".format(name=name))
    with open(file_path, "r") as f:
        return frappe.parse_json(f.read())


def create_sales_invoice(**args):
    si = frappe.new_doc("Sales Invoice")
    args = frappe._dict(args)
    abbr = args.abbr or "_TIRC"
    if args.posting_date:
        si.set_posting_time = 1

    si.posting_date = args.posting_date or nowdate()

    si.company = args.company or "_Test Indian Registered Company"
    si.customer = args.customer or "_Test Registered Customer"
    si.debit_to = args.debit_to or f"Debtors - {abbr}"
    si.update_stock = args.update_stock
    si.is_pos = args.is_pos
    si.is_return = args.is_return
    si.return_against = args.return_against
    si.currency = args.currency or "INR"
    si.conversion_rate = args.conversion_rate or 1
    si.naming_series = args.naming_series or "T-SINV-"
    si.cost_center = args.parent_cost_center
    si.is_reverse_charge = args.is_reverse_charge
    si.is_export_with_gst = args.is_export_with_gst

    if args.customer_address:
        si.customer_address = args.customer_address

    si.append(
        "items",
        {
            "item_code": args.item or args.item_code or "_Test Trading Goods 1",
            "item_name": args.item_name or "_Test Trading Goods 1",
            "description": args.description or "_Test Trading Goods 1",
            "warehouse": args.warehouse or f"Stores - {abbr}",
            "qty": args.qty or 1,
            "uom": args.uom or "Nos",
            "stock_uom": args.uom or "Nos",
            "conversion_factor": 1,
            "rate": args.rate if args.get("rate") is not None else 100,
            "price_list_rate": args.price_list_rate
            if args.get("price_list_rate") is not None
            else 100,
            "income_account": args.income_account or f"Sales - {abbr}",
            "expense_account": args.expense_account or f"Cost of Goods Sold - {abbr}",
            "discount_account": args.discount_account or None,
            "discount_amount": args.discount_amount or 0,
            "asset": args.asset or None,
            "cost_center": args.cost_center or f"Main - {abbr}",
            "serial_no": args.serial_no,
            "incoming_rate": args.incoming_rate or 0,
        },
    )

    if args.is_in_state:
        si.append("taxes", get_taxes("CGST", abbr, True))
        si.append("taxes", get_taxes("SGST", abbr, True))
    elif args.is_in_state is False:
        si.append("taxes", get_taxes("IGST", abbr, True, 18))

    if not args.do_not_save:
        si.insert()
        if not args.do_not_submit:
            si.submit()
        else:
            si.payment_schedule = []
    else:
        si.payment_schedule = []

    return si


def create_purchase_invoice(**args):
    pi = frappe.new_doc("Purchase Invoice")
    args = frappe._dict(args)
    abbr = args.abbr or "_TIRC"
    if args.posting_date:
        pi.set_posting_time = 1

    pi.posting_date = args.posting_date or nowdate()

    if args.cash_bank_account:
        pi.cash_bank_account = args.cash_bank_account

    pi.company = args.company or "_Test Indian Registered Company"
    pi.supplier = args.supplier or "_Test Registered Supplier"
    pi.currency = args.currency or "INR"
    pi.naming_series = args.naming_series or "T-PINV-"
    pi.update_stock = args.update_stock
    pi.is_paid = args.is_paid
    pi.conversion_rate = args.conversion_rate or 1
    pi.is_return = args.is_return
    pi.return_against = args.return_against
    pi.is_subcontracted = args.is_subcontracted
    pi.cost_center = args.parent_cost_center
    pi.is_reverse_charge = args.is_reverse_charge
    pi.eligibility_for_itc = args.eligibility_for_itc or "All Other ITC"

    pi.append(
        "items",
        {
            "item_code": args.item or args.item_code or "_Test Trading Goods 1",
            "warehouse": args.warehouse or f"Stores - {abbr}",
            "qty": args.qty or 5,
            "received_qty": args.received_qty or 0,
            "rejected_qty": args.rejected_qty or 0,
            "rate": args.rate or 50,
            "price_list_rate": args.price_list_rate or 50,
            "expense_account": args.expense_account or f"Cost of Goods Sold - {abbr}",
            "discount_account": args.discount_account or None,
            "discount_amount": args.discount_amount or 0,
            "conversion_factor": 1.0,
            "serial_no": args.serial_no,
            "stock_uom": args.uom or "Nos",
            "cost_center": args.cost_center or f"Main - {abbr}",
            "project": args.project,
            "rejected_warehouse": args.rejected_warehouse or "",
            "rejected_serial_no": args.rejected_serial_no or "",
            "asset_location": args.location or "",
            "allow_zero_valuation_rate": args.allow_zero_valuation_rate or 0,
        },
    )

    if args.is_in_state:
        pi.append("taxes", get_taxes("CGST", abbr))
        pi.append("taxes", get_taxes("SGST", abbr))
    elif args.is_in_state is False:
        pi.append("taxes", get_taxes("IGST", abbr, rate=18))
    elif args.is_in_state_rcm:
        pi.append("taxes", get_taxes("CGST", abbr))
        pi.append("taxes", get_taxes("SGST", abbr))
        pi.append("taxes", get_taxes("CGST RCM", abbr))
        pi.append("taxes", get_taxes("SGST RCM", abbr))
    elif args.is_in_state_rcm is False:
        pi.append("taxes", get_taxes("IGST", abbr, rate=18))
        pi.append("taxes", get_taxes("IGST RCM", abbr, rate=18))

    if not args.do_not_save:
        pi.insert()
        if not args.do_not_submit:
            pi.submit()

    return pi


def get_taxes(account, abbr, is_sales=False, rate=9):
    if is_sales:
        account_type = "Output Tax"
    else:
        account_type = "Input Tax"

    taxes = {
        "charge_type": "On Net Total",
        "account_head": f"{account_type} {account} - {abbr}",
        "description": f"{account}",
        "rate": rate,
    }

    if account.endswith("RCM"):
        taxes["add_deduct_tax"] = "Deduct"

    return taxes
