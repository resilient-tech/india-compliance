# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import random
import string

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from india_compliance.gst_india.utils.tests import create_purchase_invoice
from india_compliance.income_tax_india.overrides.company import create_tds_account
from india_compliance.income_tax_india.report.tax_withholding_details_india.tax_withholding_details_india import (
    execute,
)

COMPANY = "_Test Indian Registered Company"
ABBR = "_TIRC"
TDS_ACCOUNT = f"TDS Payable - {ABBR}"


def generate_unique_pan():
    existing_pans = set(
        frappe.get_all("Supplier", pluck="pan", filters={"pan": ("is", "set")})
        + frappe.get_all("Customer", pluck="pan", filters={"pan": ("is", "set")})
    )
    for _ in range(100):
        letters = "".join(random.choices(string.ascii_uppercase, k=5))
        digits = "".join(random.choices(string.digits, k=4))
        pan = f"{letters}{digits}{random.choice(string.ascii_uppercase)}"
        if pan not in existing_pans:
            return pan
        existing_pans.add(pan)
    raise RuntimeError("Unable to generate unique PAN")


def create_supplier(name, pan=None):
    company_currency = frappe.get_cached_value("Company", COMPANY, "default_currency")
    if not frappe.db.exists("Supplier", name):
        doc = frappe.new_doc("Supplier")
        doc.update(
            {
                "supplier_name": name,
                "supplier_type": "Individual",
                "country": "India",
                "default_currency": company_currency,
            }
        )
        doc.save()
    frappe.db.set_value(
        "Supplier", name, {"pan": pan, "country": "India", "default_currency": company_currency}
    )
    return name


def create_account(account_name, parent_account, company):
    abbr = frappe.get_cached_value("Company", company, "abbr")
    account = frappe.db.get_value("Account", f"{account_name} - {abbr}")
    if account:
        return account
    return (
        frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": account_name,
                "parent_account": parent_account,
                "company": company,
            }
        )
        .insert()
        .name
    )


def create_tax_withholding_category(category_name, account_name, **kwargs):
    fiscal_year = get_fiscal_year(today(), company=COMPANY, as_dict=True)
    tax_withholding_rate = kwargs.pop("tax_withholding_rate", 10)

    rate_row = {
        "from_date": fiscal_year.year_start_date,
        "to_date": fiscal_year.year_end_date,
        "tax_withholding_rate": tax_withholding_rate,
        "single_threshold": kwargs.pop("single_threshold", 0),
        "cumulative_threshold": kwargs.pop("cumulative_threshold", 0),
    }

    if frappe.db.exists("Tax Withholding Category", category_name):
        doc = frappe.get_doc("Tax Withholding Category", category_name)
    else:
        doc = frappe.new_doc("Tax Withholding Category")
        doc.name = category_name

    doc.update(kwargs)
    doc.set("accounts", [{"company": COMPANY, "account": account_name}])
    doc.set("rates", [rate_row])
    doc.save()
    return doc


class TestTaxWithholdingDetailsIndia(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_tds_account(COMPANY)
        cls.category = create_tax_withholding_category(
            "Test TDS Report Category",
            TDS_ACCOUNT,
            tds_section="194C",
            old_income_tax_section="194C-OLD",
            entity_type="Individual",
            single_threshold=1000,
            cumulative_threshold=1000,
            tax_withholding_rate=2,
        )
        cls.supplier = create_supplier("_Test TDS Supplier", pan=generate_unique_pan())
        frappe.db.set_value("Supplier", cls.supplier, "tax_withholding_category", cls.category.name)

        company_currency = frappe.get_cached_value("Company", COMPANY, "default_currency")
        cls.pi = create_purchase_invoice(
            supplier=cls.supplier,
            company=COMPANY,
            currency=company_currency,
            gst_category="Unregistered",
            tax_withholding_category=cls.category.name,
            apply_tds=1,
            rate=50000,
            do_not_submit=1,
        )
        cls.pi.submit()

        cls.filters = frappe._dict(
            company=COMPANY,
            party_type="Supplier",
            from_date=today(),
            to_date=today(),
        )

    def test_additional_column_and_data_in_row(self):
        columns, data = execute(self.filters)

        fieldnames = [c.get("fieldname") for c in columns]
        self.assertIn("tds_section", fieldnames)
        self.assertIn("old_income_tax_section", fieldnames)
        self.assertIn("entity_type", fieldnames)

        invoice_row = next((row for row in data if row.get("ref_no") == self.pi.name), None)
        self.assertTrue(invoice_row)
        self.assertEqual(invoice_row.get("tds_section"), "194C")
        self.assertEqual(invoice_row.get("old_income_tax_section"), "194C-OLD")
        self.assertEqual(invoice_row.get("entity_type"), "Individual")
