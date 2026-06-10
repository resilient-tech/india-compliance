# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils import getdate

from india_compliance.gst_india.utils.tests import (
    create_purchase_invoice,
    create_transaction,
)
from india_compliance.income_tax_india.utils.msme import (
    get_indian_fiscal_year,
    get_msme_due_date,
    is_section_43_b_msme_applicable,
)

COMPANY = "_Test Indian Registered Company"
FY = "2023-2024"


def get_msme_classification(supplier: str, financial_year: str) -> dict | None:
    """Classification row for a supplier in a given FY, or None if missing (test helper)."""
    rows = frappe.get_all(
        "India MSME Classification",
        filters={
            "parenttype": "Supplier",
            "parent": supplier,
            "financial_year": financial_year,
        },
        fields=["enterprise_type", "msme_applicable", "remarks"],
        limit=1,
    )
    return rows[0] if rows else None


class MSMEReportTestCase(IntegrationTestCase):
    """Shared fixtures for the MSME report tests; holds no tests itself.

    Lives here (not next to the 43B(h) report) because that report's folder
    contains parentheses - a module path plain ``import`` syntax cannot express.
    """

    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_msme_report")
        cls.supplier = cls._create_msme_supplier(enterprise_type="Micro")

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_msme_report")

    @classmethod
    def _create_msme_supplier(cls, enterprise_type, is_trader=0):
        supplier = frappe.new_doc("Supplier")
        supplier.supplier_name = frappe.generate_hash("MSME", 10)
        supplier.supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0})
        supplier.is_msme_registered = 1
        supplier.udyam_number = "UDYAM-MH-12-3456789"
        supplier.msme_is_trader = is_trader
        supplier.append(
            "india_msme_classification",
            {"financial_year": FY, "enterprise_type": enterprise_type},
        )
        supplier.insert()
        return supplier.name

    def _pi(self, supplier, posting_date, rate):
        return create_purchase_invoice(
            supplier=supplier,
            company=COMPANY,
            posting_date=posting_date,
            set_posting_time=1,  # keep the backdated posting_date
            qty=1,
            rate=rate,
        )

    def _pay(self, pi, posting_date, amount=None):
        pe = get_payment_entry("Purchase Invoice", pi.name)
        pe.posting_date = posting_date
        pe.set_posting_time = 1
        pe.reference_no = "TEST"
        pe.reference_date = posting_date
        if amount is not None:
            pe.paid_amount = amount
            pe.references[0].allocated_amount = amount
        pe.insert()
        pe.submit()
        return pe

    def _make_advance(self, supplier, payable_account, posting_date, amount):
        """Payment to the supplier not allocated against any voucher."""
        pe = create_transaction(
            doctype="Payment Entry",
            company=COMPANY,
            payment_type="Pay",
            mode_of_payment="Cash",
            party_type="Supplier",
            party=supplier,
            paid_from=self._get_cash_account(),
            paid_to=payable_account,
            paid_amount=amount,
            posting_date=posting_date,
            set_posting_time=1,
            reference_no="TEST",
            reference_date=posting_date,
            do_not_save=True,
        )
        pe.setup_party_account_field()
        pe.set_missing_values()
        pe.set_exchange_rate()
        pe.received_amount = pe.paid_amount / pe.target_exchange_rate
        pe.save()
        pe.submit()
        return pe

    @staticmethod
    def _get_cash_account():
        return frappe.db.get_value("Company", COMPANY, "default_cash_account") or (
            frappe.db.get_value("Account", {"company": COMPANY, "account_type": "Cash", "is_group": 0})
        )


class TestMSMEHelpers(UnitTestCase):
    """Pure date/applicability logic - no database, so UnitTestCase (faster)."""

    def test_indian_fiscal_year_boundaries(self):
        # March belongs to the FY that started the previous April.
        self.assertEqual(get_indian_fiscal_year("2025-03-31"), "2024-2025")
        # April starts a new FY.
        self.assertEqual(get_indian_fiscal_year("2025-04-01"), "2025-2026")
        self.assertEqual(get_indian_fiscal_year("2024-12-15"), "2024-2025")

    def test_due_date_is_posting_plus_45(self):
        self.assertEqual(getdate(get_msme_due_date("2024-01-10")), getdate("2024-02-24"))

    def test_applicability_rule(self):
        self.assertTrue(is_section_43_b_msme_applicable("Micro", 0))
        self.assertTrue(is_section_43_b_msme_applicable("Small", 0))
        # Medium is not covered by 43B(h).
        self.assertFalse(is_section_43_b_msme_applicable("Medium", 0))
        # Traders are excluded even if Micro/Small.
        self.assertFalse(is_section_43_b_msme_applicable("Small", 1))
        self.assertFalse(is_section_43_b_msme_applicable("Not MSME", 0))


class TestSupplierMSMEValidation(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_msme_supplier")

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_msme_supplier")

    def _make_supplier(self, **kwargs):
        supplier = frappe.new_doc("Supplier")
        supplier.supplier_name = frappe.generate_hash("MSME Supplier", 10)
        supplier.supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0})
        supplier.update(kwargs)
        return supplier

    def test_invalid_udyam_number_rejected(self):
        supplier = self._make_supplier(is_msme_registered=1, udyam_number="INVALID-123")
        self.assertRaises(frappe.ValidationError, supplier.insert)

    def test_valid_udyam_number_accepted_and_uppercased(self):
        supplier = self._make_supplier(is_msme_registered=1, udyam_number="udyam-mh-12-3456789")
        supplier.insert()
        self.assertEqual(supplier.udyam_number, "UDYAM-MH-12-3456789")

    def test_msme_applicable_computed_on_classification_rows(self):
        supplier = self._make_supplier(is_msme_registered=1, msme_is_trader=0)
        supplier.append(
            "india_msme_classification",
            {"financial_year": "2024-2025", "enterprise_type": "Micro"},
        )
        supplier.append(
            "india_msme_classification",
            {"financial_year": "2025-2026", "enterprise_type": "Medium"},
        )
        supplier.insert()

        micro = get_msme_classification(supplier.name, "2024-2025")
        medium = get_msme_classification(supplier.name, "2025-2026")
        self.assertTrue(micro["msme_applicable"])
        self.assertFalse(medium["msme_applicable"])
        # No row for an FY -> "Missing" (None), never inferred.
        self.assertIsNone(get_msme_classification(supplier.name, "2023-2024"))

    def test_trader_flag_excludes_micro(self):
        supplier = self._make_supplier(is_msme_registered=1, msme_is_trader=1)
        supplier.append(
            "india_msme_classification",
            {"financial_year": "2024-2025", "enterprise_type": "Small"},
        )
        supplier.insert()
        row = get_msme_classification(supplier.name, "2024-2025")
        self.assertFalse(row["msme_applicable"])

    def test_invalid_financial_year_rejected(self):
        for invalid_fy in ("2024", "2024-2026", "24-25", "FY 2024-25"):
            supplier = self._make_supplier(is_msme_registered=1)
            supplier.append(
                "india_msme_classification",
                {"financial_year": invalid_fy, "enterprise_type": "Micro"},
            )
            self.assertRaises(frappe.ValidationError, supplier.insert)

    def test_duplicate_financial_year_rejected(self):
        supplier = self._make_supplier(is_msme_registered=1)
        for enterprise_type in ("Micro", "Small"):
            supplier.append(
                "india_msme_classification",
                {"financial_year": "2024-2025", "enterprise_type": enterprise_type},
            )
        self.assertRaises(frappe.ValidationError, supplier.insert)
