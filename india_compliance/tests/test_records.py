import sys

import frappe
from frappe.desk.page.setup_wizard.setup_wizard import setup_complete
from frappe.test_runner import make_test_objects
from frappe.utils import now_datetime
from frappe.utils.nestedset import get_root_of
from erpnext.accounts.utils import get_fiscal_year

DOCTYPES = ["Company", "Item", "Customer", "Supplier", "Address"]


def before_tests():
    frappe.clear_cache()

    if not frappe.db.a_row_exists("Company"):
        now = now_datetime()
        year = now.year if now.month > 3 else now.year - 1

        setup_complete(
            {
                "currency": "INR",
                "full_name": "Test User",
                "company_name": "Wind Power LLC",
                "timezone": "Asia/Kolkata",
                "company_abbr": "WP",
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
    defaults = {
        "customer_group": get_root_of("Customer Group"),
        "supplier_group": get_root_of("Supplier Group"),
        "territory": get_root_of("Territory"),
        "item_group": get_root_of("Item Group"),
    }

    for key, value in defaults.items():
        frappe.db.set_default(key, value)

    frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)


def create_test_records():
    for doctype in DOCTYPES:
        data = getattr(sys.modules[__name__], f"test_{frappe.scrub(doctype)}_records")
        make_test_objects(doctype, data)

        if doctype != "Company":
            continue

        add_company_to_fy(data)
        setup_company_defaults(data)


def add_company_to_fy(data):
    fy = get_fiscal_year(now_datetime(), as_dict=True)
    doc = frappe.get_doc("Fiscal Year", fy.name)
    fy_companies = [row.company for row in doc.companies]

    for company in data:
        if company["company_name"] not in fy_companies:
            doc.append("companies", {"company": company["company_name"]})

    doc.save(ignore_permissions=True)


def setup_company_defaults(data):
    pass


test_company_records = [
    {
        "abbr": "_TIRC",
        "company_name": "_Test Indian Registered Company",
        "country": "India",
        "default_currency": "INR",
        "doctype": "Company",
        "domain": "Manufacturing",
        "chart_of_accounts": "Standard",
        "enable_perpetual_inventory": 0,
        "gstin": "24AAQCA8719H1ZC",
        "gst_category": "Registered Regular",
    },
    {
        "abbr": "_TIUC",
        "company_name": "_Test Indian Unregistered Company",
        "country": "India",
        "default_currency": "INR",
        "doctype": "Company",
        "domain": "Manufacturing",
        "chart_of_accounts": "Standard",
        "enable_perpetual_inventory": 0,
        "gst_category": "Unregistered",
    },
]

test_item_records = [
    {
        "description": "_Test Trading Goods 1",
        "doctype": "Item",
        "is_stock_item": 1,
        "item_code": "_Test Trading Goods 1",
        "item_name": "_Test Trading Goods 1",
        "valuation_rate": 100,
        "gst_hsn_code": "61149090",
        "item_defaults": [
            {
                "company": "_Test Indian Registered Company",
                "default_warehouse": "Stores - _TIRC",
                "expense_account": "Cost of Goods Sold - _TIRC",
                "buying_cost_center": "Main - _TIRC",
                "selling_cost_center": "Main - _TIRC",
                "income_account": "Sales - _TIRC",
            }
        ],
    }
]


test_customer_records = [
    {
        "customer_name": "_Test Registered Customer",
        "customer_type": "Company",
        "gstin": "24AANFA2641L1ZF",
        "gst_category": "Registered Regular",
    },
    {
        "customer_name": "_Test Registered Composition Customer",
        "customer_type": "Individual",
        "gstin": "24AABCR6898M1ZN",
        "gst_category": "Registered Composition",
    },
    {
        "customer_name": "_Test Unregistered Customer",
        "customer_type": "Individual",
        "gstin": "",
        "gst_category": "Unregistered",
    },
]

test_supplier_records = [
    {
        "supplier_name": "_Test Registered Supplier",
        "supplier_type": "Company",
        "gstin": "29AABCR1718E1ZL",
        "gst_category": "Registered Regular",
    },
    {
        "supplier_name": "_Test Registered Composition Supplier",
        "supplier_type": "Individual",
        "gstin": "33AAAAR6720M1ZG",
        "gst_category": "Registered Composition",
    },
    {
        "supplier_name": "_Test Unregistered Supplier",
        "supplier_type": "Individual",
        "gstin": "",
        "gst_category": "Unregistered",
    },
]

test_address_records = [
    {
        "address_type": "Billing",
        "address_line1": "Test Address - 1",
        "city": "Test City",
        "state": "Gujarat",
        "pincode": "380015",
        "country": "India",
        "gstin": "24AAQCA8719H1ZC",
        "gst_category": "Registered Regular",
        "is_primary_address": 1,
        "is_shipping_address": 1,
        "is_company_address": 1,
        "links": [
            {"link_doctype": "Company", "link_name": "_Test Indian Registered Company"}
        ],
    },
    {
        "address_type": "Billing",
        "address_line1": "Test Address - 2",
        "city": "Test City",
        "state": "Gujarat",
        "pincode": "380015",
        "country": "India",
        "gstin": "",
        "gst_category": "Unregistered",
        "is_primary_address": 1,
        "is_shipping_address": 1,
        "is_company_address": 1,
        "links": [
            {
                "link_doctype": "Company",
                "link_name": "_Test Indian Unregistered Company",
            }
        ],
    },
    {
        "address_type": "Billing",
        "address_line1": "Test Address - 3",
        "city": "Test City",
        "state": "Gujarat",
        "pincode": "380015",
        "country": "India",
        "gstin": "24AANFA2641L1ZF",
        "gst_category": "Registered Regular",
        "is_primary_address": 1,
        "is_shipping_address": 1,
        "links": [
            {"link_doctype": "Customer", "link_name": "_Test Registered Customer"}
        ],
    },
    {
        "address_type": "Billing",
        "address_line1": "Test Address - 4",
        "city": "Test City",
        "state": "Gujarat",
        "pincode": "380015",
        "country": "India",
        "gstin": "24AANCA4892J1Z8",
        "gst_category": "SEZ",
        "links": [
            {"link_doctype": "Customer", "link_name": "_Test Registered Customer"}
        ],
    },
    {
        "address_type": "Billing",
        "address_line1": "Test Address - 4",
        "city": "Test City",
        "state": "Gujarat",
        "pincode": "380015",
        "country": "India",
        "gstin": "24AABCR6898M1ZN",
        "gst_category": "Registered Regular",
        "is_primary_address": 1,
        "is_shipping_address": 1,
        "links": [
            {
                "link_doctype": "Customer",
                "link_name": "_Test Registered Composition Customer",
            }
        ],
    },
    {
        "address_type": "Billing",
        "address_line1": "Test Address - 5",
        "city": "Test City",
        "state": "Karnataka",
        "pincode": "380015",
        "country": "India",
        "gstin": "29AABCR1718E1ZL",
        "gst_category": "Registered Regular",
        "is_primary_address": 1,
        "is_shipping_address": 1,
        "links": [
            {"link_doctype": "Supplier", "link_name": "_Test Registered Supplier"}
        ],
    },
    {
        "address_type": "Billing",
        "address_line1": "Test Address - 6",
        "city": "Test City",
        "state": "Tamil Nadu",
        "pincode": "380015",
        "country": "India",
        "gstin": "33AAAAR6720M1ZG",
        "gst_category": "Registered Composition",
        "is_primary_address": 1,
        "is_shipping_address": 1,
        "links": [
            {
                "link_doctype": "Supplier",
                "link_name": "_Test Registered Composition Supplier",
            }
        ],
    },
]
