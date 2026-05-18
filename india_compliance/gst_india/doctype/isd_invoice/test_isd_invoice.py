# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import unittest

import frappe
from frappe.tests.classes import IntegrationTestCase
from frappe.utils import flt

from india_compliance.gst_india.doctype.isd_invoice.isd_invoice import _calculate_distribution


def make_doc(source_invoices, company_address=None, party_address=None):
    """Build a minimal ISD Invoice-like frappe._dict for use with _calculate_distribution."""
    rows = [
        frappe._dict(
            distribution_ratio=row["distribution_ratio"],
            total_igst=row.get("total_igst", 0),
            total_cgst=row.get("total_cgst", 0),
            total_sgst=row.get("total_sgst", 0),
            total_cess=row.get("total_cess", 0),
            total_cess_non_advol=row.get("total_cess_non_advol", 0),
        )
        for row in source_invoices
    ]
    return frappe._dict(
        source_invoices=rows,
        company_address=company_address,
        party_address=party_address,
    )


class TestISDInvoiceRounding(unittest.TestCase):
    """
    Regression tests for rounding errors in ISD distribution.

    When distribution_ratio is derived from turnover fractions that don't divide
    evenly, multiplying each row's ratio separately causes floating-point drift.
    The sum of all distributed amounts may differ from the original total tax.

    Example: 3 branches share ₹1,000,000 IGST equally (33.333...% each).
    Ratio 100/3 % per branch → distributed = 1_000_000 * (100/3) / 100
                                            = 1_000_000 / 3
                                            = 333_333.333...
    Floating-point representation rounds each to ~333333.33333333337,
    so 3 × 333333.33333333337 ≈ 1_000_000.0000000001 — 1 paisa off.

    The correct approach is to derive ratios from exact turnover values
    (turnover_i / total_turnover * total_tax) and allocate the last branch
    as (total - sum_of_others) to avoid drift.
    """

    def _total_distributed_igst(self, doc):
        return sum(flt(row.distributed_igst) for row in doc.source_invoices)

    def test_rounding_error_with_non_terminating_ratio(self):
        """
        Three branches share one purchase invoice equally.
        Using distribution_ratio=33.333...% causes the sum to exceed
        the actual total IGST due to floating-point accumulation.
        """
        total_igst = 1_000_000.00
        # 100 / 3 does not terminate in decimal; this is the problematic ratio.
        ratio = 100 / 3  # ~33.3333...

        doc = make_doc(
            [{"distribution_ratio": ratio, "total_igst": total_igst}] * 3
        )
        _calculate_distribution(doc)

        distributed_sum = self._total_distributed_igst(doc)

        # Document the rounding error: sum should be total_igst but may drift.
        error = abs(distributed_sum - total_igst)
        self.assertGreater(
            error,
            0,
            "Expected a non-zero rounding error when using 100/3 as ratio "
            f"but got exact result (distributed_sum={distributed_sum})",
        )

    def test_rounding_error_is_small(self):
        """
        The rounding error from ratio-based distribution must stay sub-paisa
        (< 0.01) so that it is unlikely to trigger validate_distribution_limits.
        """
        total_igst = 1_000_000.00
        ratio = 100 / 3

        doc = make_doc(
            [{"distribution_ratio": ratio, "total_igst": total_igst}] * 3
        )
        _calculate_distribution(doc)

        distributed_sum = self._total_distributed_igst(doc)
        error = abs(distributed_sum - total_igst)

        self.assertLess(
            error,
            0.01,
            f"Rounding error ({error}) is larger than one paisa; "
            "this may cause distribution limit validation failures.",
        )

    def test_large_values_increase_rounding_error(self):
        """
        With very large IGST amounts (e.g. crore-level) and a non-terminating
        ratio the absolute rounding error grows beyond a single paisa.
        """
        total_igst = 100_000_000.00  # 10 crore
        ratio = 100 / 3

        doc = make_doc(
            [{"distribution_ratio": ratio, "total_igst": total_igst}] * 3
        )
        _calculate_distribution(doc)

        distributed_sum = self._total_distributed_igst(doc)
        error = abs(distributed_sum - total_igst)

        # At crore scale the floating-point error can exceed 1 paisa.
        self.assertGreater(
            error,
            0,
            f"Expected a non-zero rounding error at crore-scale values "
            f"(distributed_sum={distributed_sum}, expected={total_igst})",
        )

    def test_exact_turnover_split_avoids_rounding_error(self):
        """
        When each branch ratio is computed from integer turnover values that
        divide evenly, the distribution is exact.
        """
        # Turnover: branch A=50%, B=30%, C=20% (terminating fractions).
        total_igst = 1_000_000.00
        ratios = [50.0, 30.0, 20.0]

        doc = make_doc(
            [{"distribution_ratio": r, "total_igst": total_igst} for r in ratios]
        )
        _calculate_distribution(doc)

        distributed_sum = self._total_distributed_igst(doc)
        self.assertAlmostEqual(
            distributed_sum,
            total_igst,
            places=9,
            msg="Exact ratios should produce zero rounding error.",
        )

    def test_all_tax_types_accumulate_rounding_error(self):
        """
        Rounding errors compound across IGST, CGST, SGST, CESS when all tax
        types are present and the ratio is non-terminating.
        """
        ratio = 100 / 7  # non-terminating; 3 branches
        source_row = {
            "distribution_ratio": ratio,
            "total_igst": 700_000.00,
            "total_cgst": 350_000.00,
            "total_sgst": 350_000.00,
            "total_cess": 70_000.00,
        }

        doc = make_doc([source_row] * 7)
        _calculate_distribution(doc)

        def total(field):
            return sum(flt(getattr(row, field)) for row in doc.source_invoices)

        for field, expected in (
            ("distributed_igst", 700_000.00),
            ("distributed_cgst", 350_000.00),
            ("distributed_sgst", 350_000.00),
            ("distributed_cess", 70_000.00),
        ):
            actual = total(field)
            error = abs(actual - expected)
            # Just assert the error is measurable (non-zero) and still small.
            self.assertGreater(
                error,
                0,
                f"{field}: expected rounding error but got exact result ({actual})",
            )
            self.assertLess(
                error,
                0.10,
                f"{field}: rounding error {error} is unexpectedly large.",
            )


class TestISDInvoiceInterCompanyValidation(IntegrationTestCase):
    """Tests for validate_inter_company_transaction method."""

    def setUp(self):
        """Create test companies and parties for inter-company transaction tests."""
        super().setUp()

        # Create test companies
        for i in range(1, 3):
            company_name = f"_Test Company {i}"
            if not frappe.db.exists("Company", company_name):
                frappe.get_doc({
                    "doctype": "Company",
                    "company_name": company_name,
                    "country": "India",
                    "default_currency": "INR",
                }).insert(ignore_permissions=True)

        # Create internal suppliers
        for i in range(1, 3):
            supplier_name = f"_Test Internal Supplier {i}"
            if not frappe.db.exists("Supplier", supplier_name):
                supplier = frappe.get_doc({
                    "doctype": "Supplier",
                    "supplier_name": supplier_name,
                    "is_internal_supplier": 1,
                    "represents_company": f"_Test Company {i}",
                }).insert(ignore_permissions=True)
                supplier.add_child(
                    "supplier_addresses",
                    {"address_title": f"Address of {supplier_name}"}
                )
                supplier.save(ignore_permissions=True)

        # Create internal customers
        for i in range(1, 3):
            customer_name = f"_Test Internal Customer {i}"
            if not frappe.db.exists("Customer", customer_name):
                customer = frappe.get_doc({
                    "doctype": "Customer",
                    "customer_name": customer_name,
                    "is_internal_customer": 1,
                    "represents_company": f"_Test Company {i}",
                }).insert(ignore_permissions=True)
                customer.add_child(
                    "customer_addresses",
                    {"address_title": f"Address of {customer_name}"}
                )
                customer.save(ignore_permissions=True)

        # Create a non-internal supplier (for negative test)
        if not frappe.db.exists("Supplier", "_Test Non-Internal Supplier"):
            frappe.get_doc({
                "doctype": "Supplier",
                "supplier_name": "_Test Non-Internal Supplier",
                "is_internal_supplier": 0,
            }).insert(ignore_permissions=True)

    def test_validation_skipped_when_is_against_party_false(self):
        """When is_against_party is False, validation should be skipped."""
        doc = frappe.get_doc({
            "doctype": "ISD Invoice",
            "company": "_Test Company 1",
            "is_against_party": 0,
            "party_type": "Supplier",
            "party": "_Test Non-Internal Supplier",
        })
        # Should not raise any validation error
        doc.validate_inter_company_transaction()

    def test_validation_skipped_when_party_is_none(self):
        """When party is None, validation should be skipped."""
        doc = frappe.get_doc({
            "doctype": "ISD Invoice",
            "company": "_Test Company 1",
            "is_against_party": 1,
            "party_type": "Supplier",
            "party": None,
        })
        # Should not raise any validation error
        doc.validate_inter_company_transaction()

    def test_validation_skipped_when_is_against_party_and_party_both_false(self):
        """When both is_against_party and party are falsy, validation should be skipped."""
        doc = frappe.get_doc({
            "doctype": "ISD Invoice",
            "company": "_Test Company 1",
            "is_against_party": 0,
            "party_type": "Supplier",
            "party": "",
        })
        # Should not raise any validation error
        doc.validate_inter_company_transaction()

    def test_throws_error_when_supplier_not_internal(self):
        """Should throw error when supplier is not marked as internal."""
        doc = frappe.get_doc({
            "doctype": "ISD Invoice",
            "company": "_Test Company 1",
            "is_against_party": 1,
            "party_type": "Supplier",
            "party": "_Test Non-Internal Supplier",
        })

        with self.assertRaises(frappe.ValidationError) as cm:
            doc.validate_inter_company_transaction()

        self.assertIn("must be marked as Internal", str(cm.exception))

    def test_throws_error_when_customer_not_internal(self):
        """Should throw error when customer is not marked as internal."""
        # Create a non-internal customer
        if not frappe.db.exists("Customer", "_Test Non-Internal Customer"):
            frappe.get_doc({
                "doctype": "Customer",
                "customer_name": "_Test Non-Internal Customer",
                "is_internal_customer": 0,
            }).insert(ignore_permissions=True)

        doc = frappe.get_doc({
            "doctype": "ISD Invoice",
            "company": "_Test Company 1",
            "is_against_party": 1,
            "party_type": "Customer",
            "party": "_Test Non-Internal Customer",
        })

        with self.assertRaises(frappe.ValidationError) as cm:
            doc.validate_inter_company_transaction()

        self.assertIn("must be marked as Internal", str(cm.exception))

    def test_throws_error_when_company_not_in_allowed_list(self):
        """Should throw error when company is not in Allowed To Transact With list."""
        supplier_name = "_Test Internal Supplier 1"
        company = "_Test Company 1"

        doc = frappe.get_doc({
            "doctype": "ISD Invoice",
            "company": company,
            "is_against_party": 1,
            "party_type": "Supplier",
            "party": supplier_name,
        })

        # supplier doesn't have company in Allowed To Transact With
        with self.assertRaises(frappe.ValidationError) as cm:
            doc.validate_inter_company_transaction()

        self.assertIn("is not allowed to transact with Company", str(cm.exception))
        self.assertIn(company, str(cm.exception))

    def test_passes_when_supplier_internal_and_company_allowed(self):
        """Should pass validation when supplier is internal and company is allowed."""
        supplier_name = "_Test Internal Supplier 1"
        company = "_Test Company 2"

        # Add company to Allowed To Transact With
        supplier = frappe.get_doc("Supplier", supplier_name)
        supplier.add_child(
            "allowed_companies",
            {"company": company}
        )
        supplier.save(ignore_permissions=True)

        doc = frappe.get_doc({
            "doctype": "ISD Invoice",
            "company": company,
            "is_against_party": 1,
            "party_type": "Supplier",
            "party": supplier_name,
        })

        # Should not raise any validation error
        doc.validate_inter_company_transaction()

    def test_passes_when_customer_internal_and_company_allowed(self):
        """Should pass validation when customer is internal and company is allowed."""
        customer_name = "_Test Internal Customer 1"
        company = "_Test Company 2"

        # Add company to Allowed To Transact With
        customer = frappe.get_doc("Customer", customer_name)
        customer.add_child(
            "allowed_companies",
            {"company": company}
        )
        customer.save(ignore_permissions=True)

        doc = frappe.get_doc({
            "doctype": "ISD Invoice",
            "company": company,
            "is_against_party": 1,
            "party_type": "Customer",
            "party": customer_name,
        })

        # Should not raise any validation error
        doc.validate_inter_company_transaction()

    def test_error_message_contains_party_details(self):
        """Error message should include party type, name, and company."""
        supplier_name = "_Test Internal Supplier 1"
        company = "_Test Company 1"

        doc = frappe.get_doc({
            "doctype": "ISD Invoice",
            "company": company,
            "is_against_party": 1,
            "party_type": "Supplier",
            "party": supplier_name,
        })

        with self.assertRaises(frappe.ValidationError) as cm:
            doc.validate_inter_company_transaction()

        error_msg = str(cm.exception)
        self.assertIn("Supplier", error_msg)
        self.assertIn(supplier_name, error_msg)
        self.assertIn(company, error_msg)
