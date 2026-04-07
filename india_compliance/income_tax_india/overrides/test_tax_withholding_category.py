import random
import string

import frappe
from erpnext.accounts.doctype.tax_withholding_category.tax_withholding_category import (
    get_tax_id_for_party,
)
from erpnext.accounts.utils import get_fiscal_year
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from india_compliance.gst_india.utils.tests import create_purchase_invoice

COMPANY = "_Test Indian Registered Company"
ABBR = "_TIRC"
CATEGORY = "Test PAN TDS Category"
THRESHOLD_CATEGORY = "Test PAN Threshold TDS Category"


class TestTaxWithholdingCategory(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_tds_setup()

    def test_returns_pan_for_supplier(self):
        pan = generate_unique_pan()
        supplier = create_supplier("_Test TDS Supplier With PAN", pan=pan)
        result = get_tax_id_for_party("Supplier", supplier)
        self.assertEqual(result, pan)

    def test_returns_pan_for_customer(self):
        pan = generate_unique_pan()
        customer = create_customer("_Test TDS Customer With PAN", pan=pan)
        result = get_tax_id_for_party("Customer", customer)
        self.assertEqual(result, pan)

    def test_returns_none_for_party_other_than_customer_or_supplier(self):
        party_name = "_Test TDS Employee With PAN"
        result = get_tax_id_for_party("Employee", party_name)
        self.assertEqual(result, "")

    def test_tds_deducted_and_tax_id_set_as_pan(self):
        pan = generate_unique_pan()
        supplier = create_supplier("_Test TDS PAN Supplier", pan=pan)
        frappe.db.set_value("Supplier", supplier, "tax_withholding_category", CATEGORY)

        pi = create_purchase_invoice(
            supplier=supplier,
            company=COMPANY,
            apply_tds=1,
            rate=50000,
            do_not_submit=1,
        )
        pi.submit()

        tds_amount = sum(d.base_tax_amount for d in pi.taxes if d.is_tax_withholding_account)
        self.assertEqual(tds_amount, 5000)

        twe_rows = frappe.get_all(
            "Tax Withholding Entry",
            filters={"parenttype": "Purchase Invoice", "parent": pi.name},
            fields=["name", "tax_id", "party", "party_type"],
        )
        self.assertTrue(twe_rows)
        for row in twe_rows:
            self.assertEqual(row.tax_id, pan)

    def test_threshold_considers_entries_for_parties_with_same_pan(self):
        pan = generate_unique_pan()
        suffix = frappe.generate_hash(length=6)

        supplier_1 = create_supplier(
            f"_Test TDS Shared PAN Supplier A {suffix}",
            pan=pan,
        )
        supplier_2 = create_supplier(
            f"_Test TDS Shared PAN Supplier B {suffix}",
            pan=pan,
        )

        for supplier in (supplier_1, supplier_2):
            frappe.db.set_value(
                "Supplier",
                supplier,
                "tax_withholding_category",
                THRESHOLD_CATEGORY,
            )

        pi_1 = create_purchase_invoice(
            supplier=supplier_1,
            company=COMPANY,
            apply_tds=1,
            rate=10000,
            do_not_submit=1,
        )
        pi_1.submit()

        pi_2 = create_purchase_invoice(
            supplier=supplier_2,
            company=COMPANY,
            apply_tds=1,
            rate=10000,
            do_not_submit=1,
        )
        pi_2.submit()

        pi_3 = create_purchase_invoice(
            supplier=supplier_2,
            company=COMPANY,
            apply_tds=1,
            rate=10000,
            do_not_submit=1,
        )
        pi_3.submit()

        tds_1 = sum(d.base_tax_amount for d in pi_1.taxes if d.is_tax_withholding_account)
        tds_2 = sum(d.base_tax_amount for d in pi_2.taxes if d.is_tax_withholding_account)
        tds_3 = sum(d.base_tax_amount for d in pi_3.taxes if d.is_tax_withholding_account)

        self.assertEqual(tds_1, 0)
        self.assertEqual(tds_2, 0)
        self.assertEqual(tds_3, 2000)

    def test_ldc_applies_for_party_with_same_pan(self):
        pan = generate_unique_pan()
        suffix = frappe.generate_hash(length=6)

        supplier_1 = create_supplier(
            f"_Test LDC PAN Supplier A {suffix}",
            pan=pan,
        )
        supplier_2 = create_supplier(
            f"_Test LDC PAN Supplier B {suffix}",
            pan=pan,
        )

        for supplier in (supplier_1, supplier_2):
            frappe.db.set_value("Supplier", supplier, "tax_withholding_category", CATEGORY)

        ldc_doc = create_lower_deduction_certificate(
            supplier=supplier_1,
            tax_withholding_category=CATEGORY,
            tax_rate=2,
            certificate_no=f"LDC-{suffix}",
            limit=50000,
        )

        pi = create_purchase_invoice(
            supplier=supplier_2,
            company=COMPANY,
            apply_tds=1,
            rate=10000,
            do_not_submit=1,
        )
        pi.submit()

        tds_amount = sum(d.base_tax_amount for d in pi.taxes if d.is_tax_withholding_account)
        self.assertEqual(tds_amount, 200)

        twe_rows = frappe.get_all(
            "Tax Withholding Entry",
            filters={"parenttype": "Purchase Invoice", "parent": pi.name},
            fields=["tax_id", "lower_deduction_certificate"],
        )
        self.assertTrue(twe_rows)
        self.assertEqual(twe_rows[0].tax_id, pan)
        self.assertEqual(twe_rows[0].lower_deduction_certificate, ldc_doc.name)


def create_party(party_type, name, pan=None):
    party = party_type.lower()
    if not frappe.db.exists(party_type, name):
        doc = frappe.new_doc(party_type)
        doc.update(
            {
                f"{party}_name": name,
                f"{party}_type": "Individual",
            }
        )
        doc.save()

    frappe.db.set_value(party_type, name, "pan", pan)
    return name


def create_supplier(name, pan=None):
    return create_party("Supplier", name, pan=pan)


def generate_unique_pan():
    existing_pans = frappe.get_all("Supplier", pluck="pan", filters={"pan": ("is", "set")})
    existing_pans += frappe.get_all("Customer", pluck="pan", filters={"pan": ("is", "set")})
    existing_pans = set(existing_pans)

    for _ in range(100):
        letters = "".join(random.choices(string.ascii_uppercase, k=5))
        digits = "".join(random.choices(string.digits, k=4))
        suffix = random.choice(string.ascii_uppercase)
        pan = f"{letters}{digits}{suffix}"

        if pan not in existing_pans:
            return pan

        existing_pans.add(pan)

    raise RuntimeError("Unable to generate unique PAN")


def create_customer(name, pan=None):
    return create_party("Customer", name, pan=pan)


def create_lower_deduction_certificate(
    supplier,
    tax_withholding_category,
    tax_rate,
    certificate_no,
    limit,
):
    fiscal_year = get_fiscal_year(today(), company=COMPANY)
    doc = frappe.get_doc(
        {
            "doctype": "Lower Deduction Certificate",
            "company": COMPANY,
            "supplier": supplier,
            "certificate_no": certificate_no,
            "tax_withholding_category": tax_withholding_category,
            "fiscal_year": fiscal_year[0],
            "valid_from": fiscal_year[1],
            "valid_upto": fiscal_year[2],
            "rate": tax_rate,
            "certificate_limit": limit,
        }
    ).insert(ignore_if_duplicate=True)
    return doc


def create_tax_withholding_category(category_name, account_name, **kwargs):
    fiscal_year = get_fiscal_year(today(), company=COMPANY, as_dict=True)
    tax_withholding_rate = kwargs.pop("tax_withholding_rate", 10)
    single_threshold = kwargs.pop("single_threshold", 0)
    cumulative_threshold = kwargs.pop("cumulative_threshold", 0)

    rate_row = {
        "from_date": fiscal_year.year_start_date,
        "to_date": fiscal_year.year_end_date,
        "tax_withholding_rate": tax_withholding_rate,
        "single_threshold": single_threshold,
        "cumulative_threshold": cumulative_threshold,
    }
    account_row = {"company": COMPANY, "account": account_name}

    if frappe.db.exists("Tax Withholding Category", category_name):
        doc = frappe.get_doc("Tax Withholding Category", category_name)

    else:
        doc = frappe.new_doc("Tax Withholding Category")
        doc.name = category_name

    doc.update(kwargs)
    doc.set("accounts", [account_row])
    doc.set("rates", [rate_row])
    doc.save()

    return doc


def create_account(account_name, parent_account, company):
    company_abbr = frappe.get_cached_value("Company", company, "abbr")
    account = frappe.db.get_value("Account", f"{account_name} - {company_abbr}")
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


def create_tds_setup():
    account_name = f"TDS Payable - {ABBR}"
    create_account(
        account_name="TDS Payable",
        parent_account=f"Duties and Taxes - {ABBR}",
        company=COMPANY,
    )

    create_tax_withholding_category(CATEGORY, account_name)
    create_tax_withholding_category(
        THRESHOLD_CATEGORY,
        account_name,
        disable_transaction_threshold=1,
        cumulative_threshold=30000,
    )
