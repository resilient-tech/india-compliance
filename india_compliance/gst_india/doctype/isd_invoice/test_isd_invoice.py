# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.tests import IntegrationTestCase

IGNORE_TEST_RECORD_DEPENDENCIES = [
    "ISD Invoice",
    "Cost Center",
    "Project",
    "Company",
    "Account",
    "Address",
]


def make_isd_invoice(**kwargs):
    doc = frappe.new_doc("ISD Invoice")
    doc.company = kwargs.get("company", "_Test Indian Registered Company")
    doc.posting_date = kwargs.get("posting_date", frappe.utils.today())
    doc.is_against_party = kwargs.get("is_against_party", 0)
    doc.party_type = kwargs.get("party_type")
    doc.party = kwargs.get("party")
    return doc


def make_internal_supplier(supplier_name, allowed_companies=None):
    if frappe.db.exists("Supplier", supplier_name):
        frappe.delete_doc("Supplier", supplier_name, force=True)

    supplier = frappe.get_doc(
        {
            "doctype": "Supplier",
            "supplier_name": supplier_name,
            "supplier_group": "All Supplier Groups",
            "supplier_type": "Company",
            "is_internal_supplier": 1,
        }
    )
    for company in allowed_companies or []:
        supplier.append("companies", {"company": company})
    # flags.ignore_validate skips the represents_company uniqueness check
    supplier.flags.ignore_validate = True
    supplier.insert(ignore_permissions=True)
    return supplier


def make_internal_customer(customer_name, allowed_companies=None):
    if frappe.db.exists("Customer", customer_name):
        frappe.delete_doc("Customer", customer_name, force=True)

    customer = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": customer_name,
            "customer_group": "All Customer Groups",
            "territory": "All Territories",
            "customer_type": "Company",
            "is_internal_customer": 1,
        }
    )
    for company in allowed_companies or []:
        customer.append("companies", {"company": company})
    # flags.ignore_validate skips the represents_company uniqueness check
    customer.flags.ignore_validate = True
    customer.insert(ignore_permissions=True)
    return customer


class TestISDInvoice(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = "_Test Indian Registered Company"

        cls.internal_supplier = make_internal_supplier(
            "_Test Internal Supplier ISD",
            allowed_companies=[cls.company],
        )
        cls.internal_supplier_not_allowed = make_internal_supplier(
            "_Test Internal Supplier ISD Not Allowed",
            allowed_companies=[],
        )
        cls.internal_customer = make_internal_customer(
            "_Test Internal Customer ISD",
            allowed_companies=[cls.company],
        )
        cls.internal_customer_not_allowed = make_internal_customer(
            "_Test Internal Customer ISD Not Allowed",
            allowed_companies=[],
        )

    def test_inter_company_validation_skipped_when_not_against_party(self):
        doc = make_isd_invoice(company=self.company, is_against_party=0)
        # Should not raise — is_against_party=0 means validation is skipped
        doc.validate_inter_company_transaction()

    def test_inter_company_validation_skipped_when_party_not_internal_supplier(self):
        # Non-internal supplier: is_internal_supplier=0, so validation exits early
        if not frappe.db.exists("Supplier", "_Test Supplier"):
            frappe.get_doc(
                {
                    "doctype": "Supplier",
                    "supplier_name": "_Test Supplier",
                    "supplier_group": "All Supplier Groups",
                    "supplier_type": "Company",
                }
            ).insert(ignore_permissions=True)

        doc = make_isd_invoice(
            company=self.company,
            is_against_party=1,
            party_type="Supplier",
            party="_Test Supplier",
        )
        # Should not raise — supplier is not internal
        doc.validate_inter_company_transaction()

    def test_inter_company_validation_passes_for_allowed_supplier(self):
        doc = make_isd_invoice(
            company=self.company,
            is_against_party=1,
            party_type="Supplier",
            party=self.internal_supplier.name,
        )
        # Should not raise — company is in Allowed To Transact With
        doc.validate_inter_company_transaction()

    def test_inter_company_validation_fails_for_supplier_not_allowed(self):
        doc = make_isd_invoice(
            company=self.company,
            is_against_party=1,
            party_type="Supplier",
            party=self.internal_supplier_not_allowed.name,
        )
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"is not allowed to transact with Company"),
            doc.validate_inter_company_transaction,
        )

    def test_inter_company_validation_passes_for_allowed_customer(self):
        doc = make_isd_invoice(
            company=self.company,
            is_against_party=1,
            party_type="Customer",
            party=self.internal_customer.name,
        )
        # Should not raise — company is in Allowed To Transact With
        doc.validate_inter_company_transaction()

    def test_inter_company_validation_fails_for_customer_not_allowed(self):
        doc = make_isd_invoice(
            company=self.company,
            is_against_party=1,
            party_type="Customer",
            party=self.internal_customer_not_allowed.name,
        )
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"is not allowed to transact with Company"),
            doc.validate_inter_company_transaction,
        )
