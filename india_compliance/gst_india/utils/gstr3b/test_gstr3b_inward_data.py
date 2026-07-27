import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.utils.gstr3b.gstr3b_inward_data import (
    GSTR3BCategoryConditions,
    GSTR3BInwardInvoices,
    GSTR3BSubcategory,
)


class TestGSTR3BCategoryConditions(IntegrationTestCase):
    def test_is_composition_nil_rated_or_exempted_nil_rated(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(gst_treatment="Nil-Rated")
        self.assertTrue(conditions.is_composition_nil_rated_or_exempted(invoice))

    def test_is_composition_nil_rated_or_exempted_exempted(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(gst_treatment="Exempted")
        self.assertTrue(conditions.is_composition_nil_rated_or_exempted(invoice))

    def test_is_composition_nil_rated_or_exempted_registered_composition(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(gst_treatment="Taxable", gst_category="Registered Composition")
        self.assertTrue(conditions.is_composition_nil_rated_or_exempted(invoice))

    def test_is_composition_nil_rated_or_exempted_false(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(gst_treatment="Taxable", gst_category="Registered")
        self.assertFalse(conditions.is_composition_nil_rated_or_exempted(invoice))

    def test_is_non_gst_true(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(gst_treatment="Non-GST")
        self.assertTrue(conditions.is_non_gst(invoice))

    def test_is_non_gst_false(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(gst_treatment="Taxable")
        self.assertFalse(conditions.is_non_gst(invoice))

    def test_is_itc_available_true(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(ineligibility_reason="")
        self.assertTrue(conditions.is_itc_available(invoice))

    def test_is_itc_available_poS_restricted(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(ineligibility_reason="ITC restricted due to PoS rules")
        self.assertFalse(conditions.is_itc_available(invoice))

    def test_is_ineligible_itc_true(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(ineligibility_reason="ITC restricted due to PoS rules")
        self.assertTrue(conditions.is_ineligible_itc(invoice))

    def test_is_ineligible_itc_false(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(ineligibility_reason="Some other reason")
        self.assertFalse(conditions.is_ineligible_itc(invoice))

    def test_is_itc_reversed_true(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(
            is_ineligible_for_itc=True,
            ineligibility_reason="As per rules 42 & 43 of CGST Rules and section 17(5)",
        )
        self.assertTrue(conditions.is_itc_reversed(invoice))

    def test_is_itc_reversed_not_ineligible(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(
            is_ineligible_for_itc=False,
            ineligibility_reason="",
        )
        self.assertFalse(conditions.is_itc_reversed(invoice))

    def test_is_itc_reversed_with_poS_restricted(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(
            is_ineligible_for_itc=True,
            ineligibility_reason="ITC restricted due to PoS rules",
        )
        self.assertFalse(conditions.is_itc_reversed(invoice))

    def test_is_itc_available_for_boe_always_true(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict()
        self.assertTrue(conditions.is_itc_available_for_boe(invoice))

    def test_is_itc_reversed_for_boe_true(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(is_ineligible_for_itc=True)
        self.assertTrue(conditions.is_itc_reversed_for_boe(invoice))

    def test_is_itc_reversed_for_boe_false(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(is_ineligible_for_itc=False)
        self.assertFalse(conditions.is_itc_reversed_for_boe(invoice))

    def test_is_itc_reversed_for_je_true(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(ineligibility_type="Reversal Of ITC")
        self.assertTrue(conditions.is_itc_reversed_for_je(invoice))

    def test_is_itc_reversed_for_je_false(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(ineligibility_type="Other")
        self.assertFalse(conditions.is_itc_reversed_for_je(invoice))

    def test_is_itc_reclaimed_true(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(ineligibility_type="Reclaim of ITC Reversal")
        self.assertTrue(conditions.is_itc_reclaimed(invoice))

    def test_is_itc_reclaimed_false(self):
        conditions = GSTR3BCategoryConditions()
        invoice = frappe._dict(ineligibility_type="Other")
        self.assertFalse(conditions.is_itc_reclaimed(invoice))


class TestGSTR3BSubcategory(IntegrationTestCase):
    def test_set_for_composition_nil_rated_or_exempted(self):
        sub = GSTR3BSubcategory()
        invoice = frappe._dict()
        sub.set_for_composition_nil_rated_or_exempted(invoice)
        self.assertEqual(invoice.invoice_sub_category, "Composition Scheme, Exempted, Nil Rated")

    def test_set_for_non_gst(self):
        sub = GSTR3BSubcategory()
        invoice = frappe._dict()
        sub.set_for_non_gst(invoice)
        self.assertEqual(invoice.invoice_sub_category, "Non-GST")

    def test_set_for_itc_available(self):
        sub = GSTR3BSubcategory()
        invoice = frappe._dict(itc_classification="Import Of Goods")
        sub.set_for_itc_available(invoice)
        self.assertEqual(invoice.invoice_sub_category, "Import Of Goods")

    def test_set_for_itc_reversed_others(self):
        sub = GSTR3BSubcategory()
        invoice = frappe._dict(ineligibility_reason="Others")
        sub.set_for_itc_reversed(invoice)
        self.assertEqual(invoice.invoice_sub_category, "Others")

    def test_set_for_itc_reversed_rules(self):
        sub = GSTR3BSubcategory()
        invoice = frappe._dict(ineligibility_reason="Some other reason")
        sub.set_for_itc_reversed(invoice)
        self.assertEqual(
            invoice.invoice_sub_category,
            "As per rules 42 & 43 of CGST Rules and section 17(5)",
        )

    def test_set_for_ineligible_itc(self):
        sub = GSTR3BSubcategory()
        invoice = frappe._dict()
        sub.set_for_ineligible_itc(invoice)
        self.assertEqual(invoice.invoice_sub_category, "ITC restricted due to PoS rules")

    def test_set_for_itc_available_boe(self):
        sub = GSTR3BSubcategory()
        invoice = frappe._dict()
        sub.set_for_itc_available_boe(invoice)
        self.assertEqual(invoice.invoice_sub_category, "Import Of Goods")

    def test_set_for_itc_reclaimed(self):
        sub = GSTR3BSubcategory()
        invoice = frappe._dict()
        sub.set_for_itc_reclaimed(invoice)
        self.assertEqual(invoice.invoice_sub_category, "Reclaim of ITC Reversal")


class TestGSTR3BInwardInvoices(IntegrationTestCase):
    def test_get_section_sub_categories_section_4(self):
        result = GSTR3BInwardInvoices.get_section_sub_categories(4)
        expected = [
            "Import Of Goods",
            "Import Of Service",
            "ITC on Reverse Charge",
            "Input Service Distributor",
            "All Other ITC",
            "As per rules 42 & 43 of CGST Rules and section 17(5)",
            "Others",
            "Reclaim of ITC Reversal",
            "ITC restricted due to PoS rules",
        ]
        self.assertEqual(result, expected)

    def test_get_section_sub_categories_section_5(self):
        result = GSTR3BInwardInvoices.get_section_sub_categories(5)
        expected = [
            "Composition Scheme, Exempted, Nil Rated",
            "Non-GST",
        ]
        self.assertEqual(result, expected)

    def test_get_section_sub_categories_unknown(self):
        result = GSTR3BInwardInvoices.get_section_sub_categories(99)
        self.assertEqual(result, [])

    def test_update_tax_values_inter_state(self):
        invoices = GSTR3BInwardInvoices(frappe._dict())
        invoice = frappe._dict(
            taxable_value=1000,
            invoice_category="Composition Scheme, Exempted, Nil Rated",
            place_of_supply="06-Delhi",
            company_gstin="24AAQCA8719H1ZC",
        )
        invoices.update_tax_values(invoice)
        self.assertEqual(invoice.inter, 1000)
        self.assertEqual(invoice.intra, 0)

    def test_update_tax_values_intra_state(self):
        invoices = GSTR3BInwardInvoices(frappe._dict())
        invoice = frappe._dict(
            taxable_value=1000,
            invoice_category="Composition Scheme, Exempted, Nil Rated",
            place_of_supply="24-Gujarat",
            company_gstin="24AAQCA8719H1ZC",
        )
        invoices.update_tax_values(invoice)
        self.assertEqual(invoice.inter, 0)
        self.assertEqual(invoice.intra, 1000)

    def test_update_tax_values_non_gst_intra(self):
        invoices = GSTR3BInwardInvoices(frappe._dict())
        invoice = frappe._dict(
            taxable_value=500,
            invoice_category="Non-GST",
            place_of_supply="24-Gujarat",
            company_gstin="24AAQCA8719H1ZC",
        )
        invoices.update_tax_values(invoice)
        self.assertEqual(invoice.inter, 0)
        self.assertEqual(invoice.intra, 500)

    def test_update_tax_values_itc_available_no_update(self):
        invoices = GSTR3BInwardInvoices(frappe._dict())
        invoice = frappe._dict(
            taxable_value=1000,
            invoice_category="ITC Available",
            place_of_supply="06-Delhi",
            company_gstin="24AAQCA8719H1ZC",
        )
        invoices.update_tax_values(invoice)
        self.assertEqual(invoice.inter, 0)
        self.assertEqual(invoice.intra, 0)
