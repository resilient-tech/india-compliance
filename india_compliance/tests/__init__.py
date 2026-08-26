from functools import partial

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe.desk.page.setup_wizard.setup_wizard import setup_complete
from frappe.tests.utils import make_test_objects
from frappe.utils import getdate
from frappe.utils.nestedset import get_root_of

# Tests post vouchers into past financial years and a site set up today only has
# the current one. Pinned to the oldest year any test uses rather than a rolling
# window, which would silently stop covering these dates as years pass.
#
#   2022-2023  gst_india/utils/test_utils.py
#   2023-2024  purchase_reconciliation_tool, bill_of_entry_summary, MSME
#   2025-2026  gstr_1/test_gstr_1_books_data.py
EARLIEST_TEST_FISCAL_YEAR = 2022


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
                "company_gstin": "29MUMB22923F1D",
                "default_gst_rate": "18.0",
                "enable_audit_trail": 0,
            }
        )

    set_default_settings_for_tests()
    create_fiscal_years()
    create_test_records()
    set_default_company_for_tests()
    frappe.db.commit()  # nosemgrep

    frappe.flags.country = "India"
    frappe.flags.skip_test_records = True
    frappe.enqueue = partial(frappe.enqueue, now=True)


def set_default_settings_for_tests():
    # e.g. set "All Supplier Groups" as the default Supplier Group
    for key in ("Supplier Group", "Item Group", "Territory"):
        frappe.db.set_default(frappe.scrub(key), get_root_of(key))

    # TODO: need to update for other doctypes as well
    frappe.db.set_default("customer_group", "Individual")

    # Allow Negative Stock
    frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)

    # Enable Sandbox Mode in GST Settings
    frappe.db.set_single_value("GST Settings", "sandbox_mode", 1)


def create_fiscal_years():
    """Every financial year from the oldest one tests use up to the current one.

    Left without companies, which makes a Fiscal Year apply to every company -
    see erpnext.accounts.utils._get_fiscal_years.
    """
    today = getdate()
    current_start_year = today.year if today.month > 3 else today.year - 1

    for start_year in range(EARLIEST_TEST_FISCAL_YEAR, current_start_year + 1):
        year = f"{start_year}-{start_year + 1}"

        if frappe.db.exists("Fiscal Year", year):
            continue

        frappe.get_doc(
            {
                "doctype": "Fiscal Year",
                "year": year,
                "year_start_date": f"{start_year}-04-01",
                "year_end_date": f"{start_year + 1}-03-31",
            }
        ).insert(ignore_permissions=True)


def create_test_records():
    test_records = frappe.get_file_json(frappe.get_app_path("india_compliance", "tests", "test_records.json"))

    for doctype, data in test_records.items():
        make_test_objects(doctype, data)
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
