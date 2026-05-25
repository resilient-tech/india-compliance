# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.doctype.isd_invoice.isd_invoice import bulk_create_isd_invoices
from india_compliance.gst_india.overrides.company import create_company_fixtures
from india_compliance.gst_india.utils.tests import create_purchase_invoice
from erpnext.accounts.utils import flt, get_fiscal_year

IGNORE_TEST_RECORD_DEPENDENCIES = [
    "ISD Invoice",
    "Cost Center",
    "Project",
    "Company",
    "Account",
    "Address",
    "Item Tax Template",
]

# GSTINs for test companies — Gujarat state (code 24), fictional PANs
_COMPANY_1_GSTIN = "24AAACI1681G3ZT"  # ISD company — Gujarat
_COMPANY_2_GSTIN = "24AAACI1681G1ZV"  # Branch company — Gujarat (same PAN root for inter-company)
_COMPANY_3_GSTIN = "29AAACI1681G1ZL"  # Branch company — Karnataka (same PAN root for inter-company)
_SUPPLIER_1_GSTIN = "24AAACI1681G3ZT"  # Supplier of company 1 (ISD address)
_CUSTOMER_1_GSTIN = "24AAACI1681G3ZT"  # Customer of company 1 (ISD address)
_SUPPLIER_2_GSTIN = "24AAACI1681G1ZV"  # Supplier of company 2 (non-ISD address)
_CUSTOMER_2_GSTIN = "24AAACI1681G1ZV"  # Customer of company 2 (non-ISD address)

# TODO: make this performant by adding to test_records.js
class TestISDInvoice(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # --- Company 1: main ISD company ---
        cls.company = "_Test ISD Company"
        _make_company(cls.company, "_TISD", _COMPANY_1_GSTIN)
        # Company 1 addresses
        cls.company_isd_address = _make_address(
            name=f"{cls.company}-ISD",
            gstin=_COMPANY_1_GSTIN,
            gst_category="Input Service Distributor",
            state="Gujarat",
            links=[{"link_doctype": "Company", "link_name": cls.company}],
        )
        cls.company_registered_address_gujarat = _make_address(
            name=f"{cls.company}-Registered-Gujarat",
            gstin=_COMPANY_2_GSTIN,
            gst_category="Registered Regular",
            state="Gujarat",
            links=[{"link_doctype": "Company", "link_name": cls.company}],
        )
        cls.company_registered_address_karnataka = _make_address(
            name=f"{cls.company}-Registered-Karnataka",
            gstin=_COMPANY_3_GSTIN,
            gst_category="Registered Regular",
            state="Karnataka",
            links=[{"link_doctype": "Company", "link_name": cls.company}],
            pincode="560001",
        )

        cls.company_unregistered_address = _make_address(
            name=f"{cls.company}-Unregistered",
            gstin="",
            gst_category="Unregistered",
            state="Gujarat",
            links=[{"link_doctype": "Company", "link_name": cls.company}],
        )

        # --- Company 2: sister of Company 1 ---
        cls.branch_company = "_Test ISD Branch Company"
        _make_company(cls.branch_company, "_TISDB", _COMPANY_2_GSTIN)

        # Branch company address (non-ISD, Registered Regular)
        cls.branch_company_address = _make_address(
            name=f"{cls.branch_company}-Registered",
            gstin=_COMPANY_2_GSTIN,
            gst_category="Registered Regular",
            state="Gujarat",
            links=[{"link_doctype": "Company", "link_name": cls.branch_company}],
        )


        # --- Internal supplier for Company 1 (ISD address) ---
        cls.supplier_company1 = _make_internal_supplier(
            "_Test ISD Internal Supplier C1",
            represents_company=cls.company,
            allowed_companies=[cls.branch_company],
            gstin=_SUPPLIER_1_GSTIN,
            gst_category="Input Service Distributor",
            state="Gujarat",
        )

        # --- Internal customer for Company 1 (ISD address) ---
        cls.customer_company1 = _make_internal_customer(
            "_Test ISD Internal Customer C1",
            represents_company=cls.company,
            allowed_companies=[cls.branch_company],
            gstin=_CUSTOMER_1_GSTIN,
            gst_category="Input Service Distributor",
            state="Gujarat",
        )

        # --- Internal supplier for Company 2 / Branch (non-ISD address) ---
        cls.supplier_branch = _make_internal_supplier(
            "_Test ISD Internal Supplier Branch",
            represents_company=cls.branch_company,
            allowed_companies=[cls.company],
            gstin=_SUPPLIER_2_GSTIN,
            gst_category="Registered Regular",
            state="Gujarat",
        )

        # --- Internal customer for Company 2 / Branch (non-ISD address) ---
        cls.customer_branch = _make_internal_customer(
            "_Test ISD Internal Customer Branch",
            represents_company=cls.branch_company,
            allowed_companies=[cls.company],
            gstin=_CUSTOMER_2_GSTIN,
            gst_category="Registered Regular",
            state="Gujarat",
        )

        cls.pi = create_purchase_invoice(
            company=cls.company,
            billing_address=cls.company_isd_address.name,
            supplier="_Test Registered Supplier",
            items=[{"item_code": "_Test Service Item", "qty": 1000, "rate": 1000, "gst_hsn_code": "999800"}],
            is_in_state=True,
        )
        # cgst = 90,000 and sgst = 90,000 for this PI

        cls.duplicate_isd_company = "_Test Duplicate ISD Company"
        _make_company(cls.duplicate_isd_company, "_TISDC", _COMPANY_1_GSTIN)

        # Parties not allowed to transact.
        cls.internal_supplier_not_allowed = _make_internal_supplier(
            "_Test ISD Internal Supplier Not Allowed",
            represents_company=cls.duplicate_isd_company,
            allowed_companies=[],
            gstin=_SUPPLIER_1_GSTIN,
            gst_category="Registered Regular",
            state="Gujarat",
        )
        cls.internal_customer_not_allowed = _make_internal_customer(
            "_Test ISD Internal Customer Not Allowed",
            represents_company=cls.duplicate_isd_company,
            allowed_companies=[],
            gstin=_CUSTOMER_1_GSTIN,
            gst_category="Registered Regular",
            state="Gujarat",
        )


    def test_inter_company_validation_skipped_when_not_against_party(self):
        doc = _make_isd_doc(company=self.company, is_against_party=0)
        doc.validate_inter_company_transaction()

    def test_inter_company_validation_skipped_for_non_internal_supplier(self):
        if not frappe.db.exists("Supplier", "_Test Supplier"):
            frappe.get_doc(
                {
                    "doctype": "Supplier",
                    "supplier_name": "_Test Supplier",
                    "supplier_group": "All Supplier Groups",
                    "supplier_type": "Company",
                }
            ).insert(ignore_permissions=True)

        doc = _make_isd_doc(
            company=self.company,
            is_against_party=1,
            party_type="Supplier",
            party="_Test Supplier",
        )
        doc.validate_inter_company_transaction()

    def test_inter_company_validation_passes_for_allowed_supplier(self):
        doc = _make_isd_doc(
            company=self.company,
            is_against_party=1,
            party_type="Supplier",
            party=self.supplier_branch.name,
        )
        doc.validate_inter_company_transaction()

    def test_inter_company_validation_fails_for_supplier_not_allowed(self):
        doc = _make_isd_doc(
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
        doc = _make_isd_doc(
            company=self.company,
            is_against_party=1,
            party_type="Customer",
            party=self.customer_branch.name,
        )
        doc.validate_inter_company_transaction()

    def test_inter_company_validation_fails_for_customer_not_allowed(self):
        doc = _make_isd_doc(
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

    def test_distribution_with_precise_ratios_is_accurate(self):
        """Sum of distributed taxes across all ISD invoices equals original purchase invoice taxes.

        Creates a real purchase invoice (intra-state, eligible items only), then distributes
        it across two heads with ratios 100/3 and 200/3. Verifies CGST+SGST totals are
        conserved to 2 decimal places — no rounding drift.
        """
        turnover_a = 1000000
        turnover_b = 1000000
        turnover_c = 1000000

        pi = self.pi
        pi_cgst = sum(row.cgst_amount for row in pi.items)
        pi_sgst = sum(row.sgst_amount for row in pi.items)
        pi_igst = sum(row.igst_amount for row in pi.items)
        pi_cess = sum(row.cess_amount for row in pi.items)
        pi_cess_non_advol = sum(row.cess_non_advol_amount for row in pi.items)

        rows = [
            {
                "gstin": "",
                "gst_category": "Unregistered",
                "gst_state": "Gujarat",
                "turnover_amount": turnover_a,
                "party_address": self.company_unregistered_address.name,
                "party_type": "Company",
                "party": self.company,
                "fiscal_year": get_fiscal_year(pi.posting_date, company=pi.company)[0],
            },
            {
                "gstin": _COMPANY_2_GSTIN,
                "gst_category": "Registered Regular",
                "gst_state": "Gujarat",
                "turnover_amount": turnover_b,
                "party_address": self.company_registered_address_gujarat.name,
                "party_type": "Company",
                "party": self.company,
                "fiscal_year": get_fiscal_year(pi.posting_date, company=pi.company)[0],
            },
            {
                "gstin": _COMPANY_3_GSTIN,
                "gst_category": "Registered Regular",
                "gst_state": "Karnataka",
                "turnover_amount": turnover_c,
                "party_address": self.company_registered_address_karnataka.name,
                "party_type": "Company",
                "party": self.company,
                "fiscal_year": get_fiscal_year(pi.posting_date, company=pi.company)[0],
            },
        ]
        invoice_names, _ = bulk_create_isd_invoices(distribution_heads=rows, source_names=[pi.name])

        isd_a = frappe.get_doc("ISD Invoice", invoice_names[0])
        isd_b = frappe.get_doc("ISD Invoice", invoice_names[1])
        isd_c = frappe.get_doc("ISD Invoice", invoice_names[2])

        original_total_tax = pi_cgst + pi_sgst + pi_igst + pi_cess + pi_cess_non_advol
        tax_fields = ["distributed_cgst", "distributed_sgst", "distributed_igst", "distributed_cess", "distributed_cess_non_advol"]
        distributed_total_tax = sum(
            getattr(row, field) for row in isd_a.source_invoices for field in tax_fields
        ) + sum(
            getattr(row, field) for row in isd_b.source_invoices for field in tax_fields
        ) + sum(
            getattr(row, field) for row in isd_c.source_invoices for field in tax_fields
        )

        print(f"Original total tax: {original_total_tax}"
              f"\n Distributed tax table: {[{field: getattr(row, field) for field in tax_fields} for row in isd_a.source_invoices + isd_b.source_invoices + isd_c.source_invoices]}")

        self.assertEqual(distributed_total_tax, original_total_tax)


# TODO: ask lakshit bhai about the following test cases
# >>> 16666666.666666666 * 6
# 99999999.99999996  # mathematically wrong

# >>> 16666666.666666666 + 16666666.666666666 + 16666666.666666666 + \
#     16666666.666666666 + 16666666.666666666 + 16666666.666666666
# 100000000.0  # float rounding "accidentally" gives the right answer
# is okay that python solves this problem by keeping the floating point
    def test_bulk_creation_captures_undistributed_amount_in_last_invoice(self):
        """Last ISD invoice absorbs rounding remainder so total distributed == PI total.

        CGST = SGST ≈ 100000. With 3 equal turnovers (ratio=1/3),
        100000 * (1/3) = 33333.33...
        Total distributed should be equal to original tax, so one invoice should get 33333.34 and the other two 33333.33
        """
        pi = create_purchase_invoice(
            company=self.company,
            billing_address=self.company_isd_address.name,
            supplier="_Test Registered Supplier",
            items=[{"item_code": "_Test Service Item", "qty": 1, "rate": (100/18)*200000000, "gst_hsn_code": "999800"}],
            is_in_state=True,
        )
        pi_total = sum(
            row.cgst_amount + row.sgst_amount + row.igst_amount + row.cess_amount + row.cess_non_advol_amount
            for row in pi.items
        )

        rows = [
            {
                "gstin": "",
                "gst_category": "Unregistered",
                "gst_state": "Gujarat",
                "turnover_amount": 1000000,
                "party_address": self.company_registered_address_gujarat.name,
                "party_type": "Company",
                "party": self.company,
                "fiscal_year": get_fiscal_year(pi.posting_date, company=pi.company)[0],
            },
            {
                "gstin": _COMPANY_2_GSTIN,
                "gst_category": "Registered Regular",
                "gst_state": "Gujarat",
                "turnover_amount": 1000000,
                "party_address": self.company_registered_address_gujarat.name,
                "party_type": "Company",
                "party": self.company,
                "fiscal_year": get_fiscal_year(pi.posting_date, company=pi.company)[0],
            },
            {
                "gstin": _COMPANY_3_GSTIN,
                "gst_category": "Registered Regular",
                "gst_state": "Karnataka",
                "turnover_amount": 1000000,
                "party_address": self.company_registered_address_gujarat.name,
                "party_type": "Company",
                "party": self.company,
                "fiscal_year": get_fiscal_year(pi.posting_date, company=pi.company)[0],
            },
        ]
        invoice_names, _ = bulk_create_isd_invoices(distribution_heads=rows, source_names=[pi.name])

        tax_fields = [
            "distributed_cgst", "distributed_sgst", "distributed_igst",
            "distributed_cess", "distributed_cess_non_advol",
        ]
        distributed_total = sum(
            getattr(row, f)
            for name in invoice_names
            for row in frappe.get_doc("ISD Invoice", name).source_invoices
            for f in tax_fields
        )
        print(f"Original total tax: {pi_total}")
        print(f"Distributed tax table: {[{field: getattr(row, field) for field in tax_fields} for name in invoice_names for row in frappe.get_doc('ISD Invoice', name).source_invoices]}")
        print("Distributed total tax", distributed_total)

        self.assertEqual(distributed_total, pi_total)

    # TODO: party being overseas
    # TODO: party being sez 
    def test_distribution_with_sez_recipient(self):
        """When recipient is SEZ, amount is distributed as IGST only, even for intra-state supply."""
        turnover_a = 1000000
        pi = self.pi
        # place of supply in gujarat, intra state supply

        # SEZ address
        sez_address = _make_address(
            name=f"{self.company}-SEZ",
            gstin="24AAACI1681G2ZU",
            gst_category="SEZ",
            state="Gujarat",
            links=[{"link_doctype": "Company", "link_name": self.company}],
        )

        rows = [
            {
                "gstin": "24AAACI1681G2ZU",
                "gst_category": "SEZ",
                "gst_state": "Gujarat",
                "turnover_amount": turnover_a,
                "party_address": sez_address.name,
                "party_type": "Company",
                "party": self.company,
                "fiscal_year": get_fiscal_year(pi.posting_date, company=pi.company)[0]
            }
        ]

        isd_invoices, _ = bulk_create_isd_invoices(distribution_heads=rows, source_names=[pi.name])

        # make sure they have IGST only, no CGST/SGST
        for invoice_name in isd_invoices:
            invoice = frappe.get_doc("ISD Invoice", invoice_name)
            for row in invoice.source_invoices:
                self.assertEqual(row.distributed_cgst, 0)
                self.assertEqual(row.distributed_sgst, 0)
                self.assertGreater(row.distributed_igst, 0)


    # TODO: party being overseas
    # TODO: items being non services (check using hsn code)

def _make_company(company_name, abbr, gstin, gst_category="Registered Regular", parent_company=None):
    if frappe.db.exists("Company", company_name):
        frappe.delete_doc("Company", company_name, force=True)

    doc = frappe.get_doc(
        {
            "doctype": "Company",
            "company_name": company_name,
            "abbr": abbr,
            "country": "India",
            "default_currency": "INR",
            "chart_of_accounts": "Standard",
            "gstin": gstin,
            "gst_category": gst_category,
        }
    )
    if parent_company:
        doc.parent_company = parent_company
    doc.insert(ignore_permissions=True)
    create_company_fixtures(company_name)
    return doc


def _make_address(name, gstin, gst_category, state, links, pincode="380015"):
    if frappe.db.exists("Address", name):
        frappe.delete_doc("Address", name, force=True)

    doc = frappe.get_doc(
        {
            "doctype": "Address",
            "name": name,
            "address_title": name,
            "address_type": "Billing",
            "address_line1": "Test Address Line 1",
            "city": "Test City",
            "state": state,
            "pincode": pincode,
            "country": "India",
            "gstin": gstin,
            "gst_category": gst_category,
            "is_primary_address": 1,
            "links": links,
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


def _make_isd_doc(**kwargs):
    doc = frappe.new_doc("ISD Invoice")
    doc.company = kwargs.get("company", "_Test ISD Company")
    doc.posting_date = kwargs.get("posting_date", frappe.utils.today())
    doc.is_against_party = kwargs.get("is_against_party", 0)
    doc.party_type = kwargs.get("party_type")
    doc.party = kwargs.get("party")
    return doc



def _make_internal_supplier(
    supplier_name, represents_company, allowed_companies, gstin, gst_category, state
):
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
    if represents_company:
        supplier.represents_company = represents_company
    for company in allowed_companies:
        supplier.append("companies", {"company": company})
    supplier.insert(ignore_permissions=True)

    address_name = f"{supplier_name}-Billing"
    address = _make_address(
        name=address_name,
        gstin=gstin,
        gst_category=gst_category,
        state=state,
        links=[{"link_doctype": "Supplier", "link_name": supplier.name}],
    )
    supplier.reload()
    supplier.supplier_primary_address = address.name
    supplier.save(ignore_permissions=True)

    return supplier


def _make_internal_customer(
    customer_name, represents_company, allowed_companies, gstin, gst_category, state
):
    if frappe.db.exists("Customer", customer_name):
        frappe.delete_doc("Customer", customer_name, force=True)

    customer = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": customer_name,
            "customer_type": "Company",
            "is_internal_customer": 1,
        }
    )
    if represents_company:
        customer.represents_company = represents_company
    for company in allowed_companies:
        customer.append("companies", {"company": company})
    customer.insert(ignore_permissions=True)

    address_name = f"{customer_name}-Billing"
    address = _make_address(
        name=address_name,
        gstin=gstin,
        gst_category=gst_category,
        state=state,
        links=[{"link_doctype": "Customer", "link_name": customer.name}],
    )
    customer.reload()
    customer.customer_primary_address = address.name
    customer.save(ignore_permissions=True)

    return customer
