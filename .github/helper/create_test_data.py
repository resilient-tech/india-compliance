"""
Setup test data for post-install patches testing.

This script creates an India company BEFORE India Compliance is installed.
"""

import frappe
from frappe.desk.page.setup_wizard.setup_wizard import  setup_complete
from frappe.utils.data import now_datetime


def main():
    frappe.init(site="test_site")
    frappe.connect()
    frappe.clear_cache()

    if not frappe.db.a_row_exists("Company"):
        current_year = now_datetime().year
        # Use India fiscal year (April to March)
        fy_start_year = current_year if now_datetime().month > 3 else current_year - 1

        setup_complete(
            {
                "currency": "INR",
                "full_name": "Test User",
                "company_name": "Wind Power LLP",
                "timezone": "Asia/Kolkata",
                "company_abbr": "WP",
                "industry": "Manufacturing",
                "country": "India",
                "fy_start_date": f"{fy_start_year}-04-01",
                "fy_end_date": f"{fy_start_year + 1}-03-31",
                "language": "English",
                "company_tagline": "Testing",
                "email": "test@example.com",
                "password": "test",
                "chart_of_accounts": "Standard",
                "enable_audit_trail": 0,
            }
        )



    frappe.db.commit()
    print("Test company 'Wind Power LLP' created successfully!")


if __name__ == "__main__":
    main()
