import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.utils.gstr3b.gstr3b_outward_data import (
    GSTR3BCategoryConditions,
    GSTR3BOutwardInvoices,
)


class TestGSTR3BOutwardConditions(IntegrationTestCase):
    def test_is_nil_rated_exempted_nil_rated(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(gst_treatment="Nil-Rated")
        self.assertTrue(conditions.is_nil_rated_exempted(invoice))

    def test_is_nil_rated_exempted_exempted(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(gst_treatment="Exempted")
        self.assertTrue(conditions.is_nil_rated_exempted(invoice))

    def test_is_nil_rated_exempted_false(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(gst_treatment="Taxable")
        self.assertFalse(conditions.is_nil_rated_exempted(invoice))

    def test_is_non_gst_true(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(gst_treatment="Non-GST")
        self.assertTrue(conditions.is_non_gst(invoice))

    def test_is_non_gst_false(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(gst_treatment="Taxable")
        self.assertFalse(conditions.is_non_gst(invoice))

    def test_is_ecom_9_5_true(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(ecommerce_gstin="24ABC1234", is_reverse_charge=True)
        self.assertTrue(conditions.is_ecom_9_5(invoice))

    def test_is_ecom_9_5_without_ecommerce_gstin(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(ecommerce_gstin="", is_reverse_charge=True)
        self.assertFalse(conditions.is_ecom_9_5(invoice))

    def test_is_ecom_9_5_without_reverse_charge(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(ecommerce_gstin="24ABC1234", is_reverse_charge=False)
        self.assertFalse(conditions.is_ecom_9_5(invoice))

    def test_is_zero_rated_true(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(gst_treatment="Zero-Rated")
        self.assertTrue(conditions.is_zero_rated(invoice))

    def test_is_zero_rated_false(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(gst_treatment="Taxable")
        self.assertFalse(conditions.is_zero_rated(invoice))

    def test_is_taxable_catch_all(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="",
            is_reverse_charge=False,
        )
        self.assertTrue(conditions.is_taxable(invoice))

    def test_is_taxable_nil_rated_excluded(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(gst_treatment="Nil-Rated")
        self.assertFalse(conditions.is_taxable(invoice))

    def test_is_taxable_non_gst_excluded(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(gst_treatment="Non-GST")
        self.assertFalse(conditions.is_taxable(invoice))

    def test_is_taxable_ecom_9_5_excluded(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="24ABC1234",
            is_reverse_charge=True,
        )
        self.assertFalse(conditions.is_taxable(invoice))

    def test_is_taxable_zero_rated_excluded(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(gst_treatment="Zero-Rated")
        self.assertFalse(conditions.is_taxable(invoice))

    def test_is_inward_reverse_charge_true(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(is_reverse_charge=True)
        self.assertTrue(conditions.is_inward_reverse_charge(invoice))

    def test_is_inward_reverse_charge_false(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(is_reverse_charge=False)
        self.assertFalse(conditions.is_inward_reverse_charge(invoice))


class TestGSTR3BOutwardInvoices(IntegrationTestCase):
    def test_is_part_of_inter_state_supplies_all_conditions(self):
        invoices = GSTR3BOutwardInvoices(frappe._dict())
        result = invoices.is_part_of_inter_state_supplies(
            frappe._dict(
                invoice_sub_category="Taxable",
                gst_category="Unregistered",
                igst_amount=100,
                gst_rate=18,
            ),
            "Sales Invoice",
        )
        self.assertTrue(result)

    def test_is_part_of_inter_state_supplies_wrong_doctype(self):
        invoices = GSTR3BOutwardInvoices(frappe._dict())
        result = invoices.is_part_of_inter_state_supplies(
            frappe._dict(
                invoice_sub_category="Taxable",
                gst_category="Unregistered",
                igst_amount=100,
                gst_rate=18,
            ),
            "Purchase Invoice",
        )
        self.assertFalse(result)

    def test_is_part_of_inter_state_supplies_not_taxable(self):
        invoices = GSTR3BOutwardInvoices(frappe._dict())
        result = invoices.is_part_of_inter_state_supplies(
            frappe._dict(
                invoice_sub_category="Zero-Rated",
                gst_category="Unregistered",
                igst_amount=100,
                gst_rate=18,
            ),
            "Sales Invoice",
        )
        self.assertFalse(result)

    def test_is_part_of_inter_state_supplies_not_in_inter_state_categories(self):
        invoices = GSTR3BOutwardInvoices(frappe._dict())
        result = invoices.is_part_of_inter_state_supplies(
            frappe._dict(
                invoice_sub_category="Taxable",
                gst_category="Registered",
                igst_amount=100,
                gst_rate=18,
            ),
            "Sales Invoice",
        )
        self.assertFalse(result)

    def test_is_part_of_inter_state_supplies_no_igst(self):
        invoices = GSTR3BOutwardInvoices(frappe._dict())
        result = invoices.is_part_of_inter_state_supplies(
            frappe._dict(
                invoice_sub_category="Taxable",
                gst_category="Unregistered",
                igst_amount=0,
                gst_rate=18,
            ),
            "Sales Invoice",
        )
        self.assertFalse(result)

    def test_is_part_of_inter_state_supplies_no_gst_rate(self):
        invoices = GSTR3BOutwardInvoices(frappe._dict())
        result = invoices.is_part_of_inter_state_supplies(
            frappe._dict(
                invoice_sub_category="Taxable",
                gst_category="Unregistered",
                igst_amount=100,
                gst_rate=0,
            ),
            "Sales Invoice",
        )
        self.assertFalse(result)

    def test_set_tax_amounts_rcm_sales_invoice(self):
        invoices = GSTR3BOutwardInvoices(frappe._dict())
        invoice = frappe._dict(
            is_reverse_charge=True,
            igst_amount=100,
            cgst_amount=50,
            sgst_amount=50,
            total_cess_amount=10,
        )
        invoices.set_tax_amounts(invoice, "Sales Invoice")
        self.assertEqual(invoice.igst_amount, 0)
        self.assertEqual(invoice.cgst_amount, 0)
        self.assertEqual(invoice.sgst_amount, 0)
        self.assertEqual(invoice.total_cess_amount, 0)

    def test_set_tax_amounts_non_rcm_sales_invoice(self):
        invoices = GSTR3BOutwardInvoices(frappe._dict())
        invoice = frappe._dict(
            is_reverse_charge=False,
            igst_amount=100,
            cgst_amount=50,
            sgst_amount=50,
            total_cess_amount=10,
        )
        invoices.set_tax_amounts(invoice, "Sales Invoice")
        self.assertEqual(invoice.igst_amount, 100)
        self.assertEqual(invoice.cgst_amount, 50)
        self.assertEqual(invoice.sgst_amount, 50)
        self.assertEqual(invoice.total_cess_amount, 10)

    def test_set_tax_amounts_purchase_invoice_ignored(self):
        invoices = GSTR3BOutwardInvoices(frappe._dict())
        invoice = frappe._dict(
            is_reverse_charge=True,
            igst_amount=100,
            cgst_amount=50,
            sgst_amount=50,
            total_cess_amount=10,
        )
        invoices.set_tax_amounts(invoice, "Purchase Invoice")
        self.assertEqual(invoice.igst_amount, 100)
        self.assertEqual(invoice.cgst_amount, 50)
        self.assertEqual(invoice.sgst_amount, 50)
        self.assertEqual(invoice.total_cess_amount, 10)

    def test_get_advance_adjustment_rows_basic_structure(self):
        invoices = GSTR3BOutwardInvoices(frappe._dict())
        rows = invoices.get_advance_adjustment_rows(
            [
                frappe._dict(
                    invoice_no="ADV-001",
                    customer_name="Test Customer",
                    posting_date="2025-01-15",
                    company_gstin="24AAQCA8719H1ZC",
                    place_of_supply="06-Delhi",
                    taxable_value=1000,
                    tax_amount=180,
                    cess_amount=10,
                ),
            ],
            1,
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.invoice_category, "Details of Outward Supplies and inward supplies liable to reverse charge")
        self.assertEqual(row.invoice_sub_category, "Taxable")
        self.assertEqual(row.voucher_type, "Payment Entry")
        self.assertEqual(row.gst_rate, 18)
        self.assertEqual(row.igst_amount, 180)
        self.assertEqual(row.cgst_amount, 0)
        self.assertEqual(row.sgst_amount, 0)

    def test_get_advance_adjustment_rows_intra_state(self):
        invoices = GSTR3BOutwardInvoices(frappe._dict())
        rows = invoices.get_advance_adjustment_rows(
            [
                frappe._dict(
                    invoice_no="ADV-001",
                    customer_name="Test Customer",
                    posting_date="2025-01-15",
                    company_gstin="24AAQCA8719H1ZC",
                    place_of_supply="24-Gujarat",
                    taxable_value=1000,
                    tax_amount=180,
                    cess_amount=10,
                ),
            ],
            1,
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.igst_amount, 0)
        self.assertEqual(row.cgst_amount, 90)
        self.assertEqual(row.sgst_amount, 90)

    def test_get_advance_adjustment_rows_zero_taxable_value(self):
        invoices = GSTR3BOutwardInvoices(frappe._dict())
        rows = invoices.get_advance_adjustment_rows(
            [
                frappe._dict(
                    invoice_no="ADV-001",
                    customer_name="Test Customer",
                    posting_date="2025-01-15",
                    company_gstin="24AAQCA8719H1ZC",
                    place_of_supply="06-Delhi",
                    taxable_value=0,
                    tax_amount=0,
                    cess_amount=0,
                ),
            ],
            1,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].gst_rate, 0)

    def test_get_advance_adjustment_rows_with_return_against(self):
        invoices = GSTR3BOutwardInvoices(frappe._dict())
        rows = invoices.get_advance_adjustment_rows(
            [
                frappe._dict(
                    invoice_no="ADJ-001",
                    customer_name="Test Customer",
                    posting_date="2025-01-15",
                    company_gstin="24AAQCA8719H1ZC",
                    place_of_supply="06-Delhi",
                    taxable_value=500,
                    tax_amount=90,
                    cess_amount=5,
                    return_against="ADV-001",
                ),
            ],
            -1,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].return_against, "ADV-001")
        self.assertEqual(rows[0].taxable_value, -500)
