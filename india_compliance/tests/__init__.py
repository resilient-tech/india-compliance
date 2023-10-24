from functools import partial

import frappe
from frappe.desk.page.setup_wizard.setup_wizard import setup_complete
from frappe.test_runner import make_test_objects
from frappe.utils import getdate
from frappe.utils.nestedset import get_root_of
from erpnext.accounts.utils import get_fiscal_year


def before_tests():
    frappe.clear_cache()

    if not frappe.db.a_row_exists("Company"):
        today = getdate()
        year = today.year if today.month > 3 else today.year - 1

        setup_complete(
            {
                "currency": "INR",
                "full_name": "Test User",
                "company_name": "Wind Power LLP",
                "timezone": "Asia/Kolkata",
                "company_abbr": "WP",
                "industry": "Manufacturing",
                "country": "India",
                "fy_start_date": f"{year}-04-01",
                "fy_end_date": f"{year + 1}-03-31",
                "language": "English",
                "company_tagline": "Testing",
                "email": "test@example.com",
                "password": "test",
                "chart_of_accounts": "Standard",
            }
        )

    set_default_settings_for_tests()
    create_test_records()
    set_default_company_for_tests()
    frappe.db.commit()

    frappe.flags.country = "India"
    frappe.flags.skip_test_records = True
    frappe.enqueue = partial(frappe.enqueue, now=True)


def set_default_settings_for_tests():
    # e.g. set "All Customer Groups" as the default Customer Group
    for key in ("Customer Group", "Supplier Group", "Item Group", "Territory"):
        frappe.db.set_default(frappe.scrub(key), get_root_of(key))

    # Allow Negative Stock
    frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)

    # Enable Sandbox Mode in GST Settings
    frappe.db.set_single_value("GST Settings", "sandbox_mode", 1)


def create_test_records():
    test_records = frappe.get_file_json(
        frappe.get_app_path("india_compliance", "tests", "test_records.json")
    )

    for doctype, data in test_records.items():
        make_test_objects(doctype, data, reset=True)
        if doctype == "Company":
            add_companies_to_fiscal_year(data)


def set_default_company_for_tests():
    # stock settings
    frappe.db.set_value(
        "Company",
        "_Test Indian Registered Company",
        {
            "enable_perpetual_inventory": 1,
            "default_inventory_account": "Stock In Hand - _TIRC",
            "stock_adjustment_account": "Stock Adjustment - _TIRC",
            "stock_received_but_not_billed": "Stock Received But Not Billed - _TIRC",
            "expenses_included_in_valuation": "Expenses Included In Valuation - _TIRC",
        },
    )

    # set default company
    global_defaults = frappe.get_single("Global Defaults")
    global_defaults.default_company = "_Test Indian Registered Company"
    global_defaults.save()


def add_companies_to_fiscal_year(data):
    fy = get_fiscal_year(getdate(), as_dict=True)
    doc = frappe.get_doc("Fiscal Year", fy.name)
    fy_companies = [row.company for row in doc.companies]

    for company in data:
        if (company_name := company["company_name"]) not in fy_companies:
            doc.append("companies", {"company": company_name})

    doc.save(ignore_permissions=True)
