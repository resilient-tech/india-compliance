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
    # frappe.db.commit()


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

    if args.taxes == "in-state":
        si.append(
            "taxes",
            {
                "charge_type": "On Net Total",
                "account_head": f"Output Tax SGST - {abbr}",
                "description": "SGST",
                "rate": 9,
            },
        )
        si.append(
            "taxes",
            {
                "charge_type": "On Net Total",
                "account_head": f"Output Tax CGST - {abbr}",
                "description": "CGST",
                "rate": 9,
            },
        )
    elif args.taxes == "out-of-state":
        si.append(
            "taxes",
            {
                "charge_type": "On Net Total",
                "account_head": f"Output Tax IGST - {abbr}",
                "description": "IGST",
                "rate": 18,
            },
        )

    if not args.do_not_save:
        si.insert()
        if not args.do_not_submit:
            si.submit()
        else:
            si.payment_schedule = []
    else:
        si.payment_schedule = []

    return si
