import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from india_compliance.gst_india.utils.gstr_1.gstr_1_data import (
    GSTR1CategoryConditions,
    GSTR1Conditions,
    GSTR1DocumentIssuedSummary,
    GSTR1Subcategory,
    GSTR11A11BData,
)


class TestGSTR1Conditions(IntegrationTestCase):
    def test_is_nil_rated_returns_true(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(gst_treatment="Nil-Rated")
        self.assertTrue(conditions.is_nil_rated(invoice))

    def test_is_nil_rated_returns_false(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(gst_treatment="Taxable")
        self.assertFalse(conditions.is_nil_rated(invoice))

    def test_is_nil_rated_empty_treatment(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(gst_treatment="")
        self.assertFalse(conditions.is_nil_rated(invoice))

    def test_is_exempted_returns_true(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(gst_treatment="Exempted")
        self.assertTrue(conditions.is_exempted(invoice))

    def test_is_exempted_returns_false(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(gst_treatment="Nil-Rated")
        self.assertFalse(conditions.is_exempted(invoice))

    def test_is_non_gst_returns_true(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(gst_treatment="Non-GST")
        self.assertTrue(conditions.is_non_gst(invoice))

    def test_is_non_gst_returns_false(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(gst_treatment="Taxable")
        self.assertFalse(conditions.is_non_gst(invoice))

    def test_is_nil_rated_exempted_or_non_gst_with_nil_rated(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(
            gst_treatment="Nil-Rated",
            place_of_supply="06-Delhi",
            gst_category="Registered",
        )
        self.assertTrue(conditions.is_nil_rated_exempted_or_non_gst(invoice))

    def test_is_nil_rated_exempted_or_non_gst_with_exempted(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(
            gst_treatment="Exempted",
            place_of_supply="06-Delhi",
            gst_category="Registered",
        )
        self.assertTrue(conditions.is_nil_rated_exempted_or_non_gst(invoice))

    def test_is_nil_rated_exempted_or_non_gst_with_non_gst(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(
            gst_treatment="Non-GST",
            place_of_supply="06-Delhi",
            gst_category="Registered",
        )
        self.assertTrue(conditions.is_nil_rated_exempted_or_non_gst(invoice))

    def test_is_nil_rated_exempted_or_non_gst_export_returns_false(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(
            gst_treatment="Nil-Rated",
            place_of_supply="96-Other Countries",
            gst_category="Overseas",
        )
        self.assertFalse(conditions.is_nil_rated_exempted_or_non_gst(invoice))

    def test_is_nil_rated_exempted_or_non_gst_taxable_returns_false(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            place_of_supply="06-Delhi",
            gst_category="Registered",
        )
        self.assertFalse(conditions.is_nil_rated_exempted_or_non_gst(invoice))

    def test_is_cn_dn_with_is_return(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(is_return=True, is_debit_note=False)
        self.assertTrue(conditions.is_cn_dn(invoice))

    def test_is_cn_dn_with_is_debit_note(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(is_return=False, is_debit_note=True)
        self.assertTrue(conditions.is_cn_dn(invoice))

    def test_is_cn_dn_with_neither(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(is_return=False, is_debit_note=False)
        self.assertFalse(conditions.is_cn_dn(invoice))

    def test_is_ecom_rcm_with_both_flags(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(ecommerce_gstin="24ABC1234", is_reverse_charge=True)
        self.assertTrue(conditions.is_ecom_rcm(invoice))

    def test_is_ecom_rcm_without_ecommerce_gstin(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(ecommerce_gstin="", is_reverse_charge=True)
        self.assertFalse(conditions.is_ecom_rcm(invoice))

    def test_is_ecom_rcm_without_reverse_charge(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(ecommerce_gstin="24ABC1234", is_reverse_charge=False)
        self.assertFalse(conditions.is_ecom_rcm(invoice))

    def test_is_ecom_rcm_with_neither(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(ecommerce_gstin="", is_reverse_charge=False)
        self.assertFalse(conditions.is_ecom_rcm(invoice))

    def test_is_export_with_overseas_and_place_of_supply_96(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(place_of_supply="96-Other Countries", gst_category="Overseas")
        self.assertTrue(conditions.is_export(invoice))

    def test_is_export_with_overseas_wrong_pos(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(place_of_supply="06-Delhi", gst_category="Overseas")
        self.assertFalse(conditions.is_export(invoice))

    def test_is_export_with_wrong_category(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(place_of_supply="96-Other Countries", gst_category="Registered")
        self.assertFalse(conditions.is_export(invoice))

    def test_has_gstin_and_is_not_export_with_gstin(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(
            billing_address_gstin="24ABCDE1234",
            place_of_supply="06-Delhi",
            gst_category="Registered",
        )
        self.assertTrue(conditions.has_gstin_and_is_not_export(invoice))

    def test_has_gstin_and_is_not_export_without_gstin(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(
            billing_address_gstin="",
            place_of_supply="06-Delhi",
            gst_category="Registered",
        )
        self.assertFalse(conditions.has_gstin_and_is_not_export(invoice))

    def test_has_gstin_and_is_not_export_with_export(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(
            billing_address_gstin="24ABCDE1234",
            place_of_supply="96-Other Countries",
            gst_category="Overseas",
        )
        self.assertFalse(conditions.has_gstin_and_is_not_export(invoice))

    def test_is_inter_state_different_states(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(company_gstin="24AAQCA8719H1ZC", place_of_supply="06-Delhi")
        self.assertTrue(conditions.is_inter_state(invoice))

    def test_is_inter_state_same_state(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(company_gstin="24AAQCA8719H1ZC", place_of_supply="24-Gujarat")
        self.assertFalse(conditions.is_inter_state(invoice))

    def test_is_inter_state_no_place_of_supply(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(company_gstin="24AAQCA8719H1ZC", place_of_supply="")
        self.assertFalse(conditions.is_inter_state(invoice))

    def test_is_b2cl_inv_above_limit_inter_state(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(
            invoice_total=300000,
            posting_date=getdate("2025-01-01"),
            company_gstin="24AAQCA8719H1ZC",
            place_of_supply="06-Delhi",
        )
        self.assertTrue(conditions.is_b2cl_inv(invoice))

    def test_is_b2cl_inv_below_limit(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(
            invoice_total=50000,
            posting_date=getdate("2025-01-01"),
            company_gstin="24AAQCA8719H1ZC",
            place_of_supply="06-Delhi",
        )
        self.assertFalse(conditions.is_b2cl_inv(invoice))

    def test_is_b2cl_inv_intra_state(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(
            invoice_total=300000,
            posting_date=getdate("2025-01-01"),
            company_gstin="24AAQCA8719H1ZC",
            place_of_supply="24-Gujarat",
        )
        self.assertFalse(conditions.is_b2cl_inv(invoice))

    def test_is_b2cl_cn_dn_with_return_above_limit(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(
            invoice_total=50000,
            returned_invoice_total=300000,
            return_against="INV-001",
            posting_date=getdate("2025-01-01"),
            company_gstin="24AAQCA8719H1ZC",
            place_of_supply="06-Delhi",
        )
        self.assertTrue(conditions.is_b2cl_cn_dn(invoice))

    def test_is_b2cl_cn_dn_without_return_below_limit(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(
            invoice_total=50000,
            posting_date=getdate("2025-01-01"),
            company_gstin="24AAQCA8719H1ZC",
            place_of_supply="06-Delhi",
        )
        self.assertFalse(conditions.is_b2cl_cn_dn(invoice))

    def test_cache_invoice_condition_caches_result(self):
        conditions = GSTR1Conditions()
        invoice = frappe._dict(gst_treatment="Nil-Rated")
        self.assertTrue(conditions.is_nil_rated(invoice))

        invoice.gst_treatment = "Taxable"
        self.assertTrue(conditions.is_nil_rated(invoice))


class TestGSTR1CategoryConditions(IntegrationTestCase):
    def test_is_b2b_invoice_all_conditions_met(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="",
            is_reverse_charge=False,
            is_return=False,
            is_debit_note=False,
            billing_address_gstin="24ABCDE1234",
            place_of_supply="06-Delhi",
            gst_category="Registered",
        )
        self.assertTrue(conditions.is_b2b_invoice(invoice))

    def test_is_b2b_invoice_ecom_rcm_excluded(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="24ABC1234",
            is_reverse_charge=True,
            is_return=False,
            is_debit_note=False,
            billing_address_gstin="24ABCDE1234",
            place_of_supply="06-Delhi",
            gst_category="Registered",
        )
        self.assertFalse(conditions.is_b2b_invoice(invoice))

    def test_is_b2b_invoice_nil_rated_excluded(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Nil-Rated",
            ecommerce_gstin="",
            is_reverse_charge=False,
            is_return=False,
            is_debit_note=False,
            billing_address_gstin="24ABCDE1234",
            place_of_supply="06-Delhi",
            gst_category="Registered",
        )
        self.assertFalse(conditions.is_b2b_invoice(invoice))

    def test_is_b2b_invoice_cn_dn_excluded(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="",
            is_reverse_charge=False,
            is_return=True,
            is_debit_note=False,
            billing_address_gstin="24ABCDE1234",
            place_of_supply="06-Delhi",
            gst_category="Registered",
        )
        self.assertFalse(conditions.is_b2b_invoice(invoice))

    def test_is_b2b_invoice_no_gstin_excluded(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="",
            is_reverse_charge=False,
            is_return=False,
            is_debit_note=False,
            billing_address_gstin="",
            place_of_supply="06-Delhi",
            gst_category="Registered",
        )
        self.assertFalse(conditions.is_b2b_invoice(invoice))

    def test_is_export_invoice_all_conditions_met(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="",
            is_reverse_charge=False,
            is_return=False,
            is_debit_note=False,
            place_of_supply="96-Other Countries",
            gst_category="Overseas",
        )
        self.assertTrue(conditions.is_export_invoice(invoice))

    def test_is_export_invoice_ecom_rcm_excluded(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="24ABC1234",
            is_reverse_charge=True,
            is_return=False,
            is_debit_note=False,
            place_of_supply="96-Other Countries",
            gst_category="Overseas",
        )
        self.assertFalse(conditions.is_export_invoice(invoice))

    def test_is_b2cl_invoice_all_conditions_met(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="",
            is_reverse_charge=False,
            is_return=False,
            is_debit_note=False,
            billing_address_gstin="",
            place_of_supply="06-Delhi",
            gst_category="Unregistered",
            invoice_total=300000,
            posting_date=getdate("2025-01-01"),
            company_gstin="24AAQCA8719H1ZC",
        )
        self.assertTrue(conditions.is_b2cl_invoice(invoice))

    def test_is_b2cl_invoice_has_gstin_excluded(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="",
            is_reverse_charge=False,
            is_return=False,
            is_debit_note=False,
            billing_address_gstin="24ABCDE1234",
            place_of_supply="06-Delhi",
            gst_category="Unregistered",
            invoice_total=300000,
            posting_date=getdate("2025-01-01"),
            company_gstin="24AAQCA8719H1ZC",
        )
        self.assertFalse(conditions.is_b2cl_invoice(invoice))

    def test_is_b2cs_invoice_fallback(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="",
            is_reverse_charge=False,
            is_return=False,
            is_debit_note=False,
            billing_address_gstin="",
            place_of_supply="24-Gujarat",
            gst_category="Unregistered",
            invoice_total=50000,
            posting_date=getdate("2025-01-01"),
            company_gstin="24AAQCA8719H1ZC",
        )
        self.assertTrue(conditions.is_b2cs_invoice(invoice))

    def test_is_b2cs_invoice_with_b2cl_inv_excluded(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="",
            is_reverse_charge=False,
            is_return=False,
            is_debit_note=False,
            billing_address_gstin="",
            place_of_supply="06-Delhi",
            gst_category="Unregistered",
            invoice_total=300000,
            posting_date=getdate("2025-01-01"),
            company_gstin="24AAQCA8719H1ZC",
        )
        self.assertFalse(conditions.is_b2cs_invoice(invoice))

    def test_is_cdnr_invoice_all_conditions_met(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="",
            is_reverse_charge=False,
            is_return=True,
            is_debit_note=False,
            billing_address_gstin="24ABCDE1234",
            place_of_supply="06-Delhi",
            gst_category="Registered",
        )
        self.assertTrue(conditions.is_cdnr_invoice(invoice))

    def test_is_cdnr_invoice_without_gstin_excluded(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="",
            is_reverse_charge=False,
            is_return=True,
            is_debit_note=False,
            billing_address_gstin="",
            place_of_supply="06-Delhi",
            gst_category="Unregistered",
        )
        self.assertFalse(conditions.is_cdnr_invoice(invoice))

    def test_is_cdnur_invoice_export(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="",
            is_reverse_charge=False,
            is_return=True,
            is_debit_note=False,
            billing_address_gstin="",
            place_of_supply="96-Other Countries",
            gst_category="Overseas",
        )
        self.assertTrue(conditions.is_cdnur_invoice(invoice))

    def test_is_cdnur_invoice_b2cl(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="",
            is_reverse_charge=False,
            is_return=True,
            is_debit_note=False,
            billing_address_gstin="",
            place_of_supply="06-Delhi",
            gst_category="Unregistered",
            invoice_total=300000,
            returned_invoice_total=0,
            posting_date=getdate("2025-01-01"),
            company_gstin="24AAQCA8719H1ZC",
        )
        self.assertTrue(conditions.is_cdnur_invoice(invoice))

    def test_is_cdnur_invoice_unregistered_intra_below_limit_excluded(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Taxable",
            ecommerce_gstin="",
            is_reverse_charge=False,
            is_return=True,
            is_debit_note=False,
            billing_address_gstin="",
            place_of_supply="24-Gujarat",
            gst_category="Unregistered",
            invoice_total=50000,
            posting_date=getdate("2025-01-01"),
            company_gstin="24AAQCA8719H1ZC",
        )
        self.assertFalse(conditions.is_cdnur_invoice(invoice))

    def test_is_nil_rated_exempted_non_gst_invoice_with_nil(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Nil-Rated",
            ecommerce_gstin="",
            is_reverse_charge=False,
        )
        self.assertTrue(conditions.is_nil_rated_exempted_non_gst_invoice(invoice))

    def test_is_nil_rated_exempted_non_gst_invoice_ecom_excluded(self):
        conditions = GSTR1CategoryConditions()
        invoice = frappe._dict(
            gst_treatment="Nil-Rated",
            ecommerce_gstin="24ABC1234",
            is_reverse_charge=True,
        )
        self.assertFalse(conditions.is_nil_rated_exempted_non_gst_invoice(invoice))


class TestGSTR1Subcategory(IntegrationTestCase):
    def test_set_for_b2b_calls_invoice_type_method(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict(
            gst_category="Registered",
            is_reverse_charge=False,
            is_export_with_gst=False,
        )
        sub.set_for_b2b(invoice)
        self.assertEqual(invoice.invoice_sub_category, "B2B Regular")

    def test_set_for_b2b_deemed_export(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict(
            gst_category="Deemed Export",
            is_reverse_charge=False,
            is_export_with_gst=False,
        )
        sub.set_for_b2b(invoice)
        self.assertEqual(invoice.invoice_type, "Deemed Exp")
        self.assertEqual(invoice.invoice_sub_category, "Deemed Exports")

    def test_set_for_b2b_sez_with_gst(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict(
            gst_category="SEZ",
            is_reverse_charge=False,
            is_export_with_gst=True,
        )
        sub.set_for_b2b(invoice)
        self.assertEqual(invoice.invoice_type, "SEZ supplies with payment")
        self.assertEqual(invoice.invoice_sub_category, "SEZ With Payment of Tax")

    def test_set_for_b2b_sez_without_gst(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict(
            gst_category="SEZ",
            is_reverse_charge=False,
            is_export_with_gst=False,
        )
        sub.set_for_b2b(invoice)
        self.assertEqual(invoice.invoice_type, "SEZ supplies without payment")
        self.assertEqual(invoice.invoice_sub_category, "SEZ Without Payment of Tax")

    def test_set_for_b2b_reverse_charge(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict(
            gst_category="Registered",
            is_reverse_charge=True,
            is_export_with_gst=False,
        )
        sub.set_for_b2b(invoice)
        self.assertEqual(invoice.invoice_type, "Regular B2B")
        self.assertEqual(invoice.invoice_sub_category, "B2B Reverse Charge")

    def test_set_for_b2b_regular(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict(
            gst_category="Registered",
            is_reverse_charge=False,
            is_export_with_gst=False,
        )
        sub.set_for_b2b(invoice)
        self.assertEqual(invoice.invoice_type, "Regular B2B")
        self.assertEqual(invoice.invoice_sub_category, "B2B Regular")

    def test_set_for_b2cl(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict()
        sub.set_for_b2cl(invoice)
        self.assertEqual(invoice.invoice_sub_category, "B2C (Large)")

    def test_set_for_exports_with_gst(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict(is_export_with_gst=True)
        sub.set_for_exports(invoice)
        self.assertEqual(invoice.invoice_sub_category, "Export With Payment of Tax")
        self.assertEqual(invoice.invoice_type, "WPAY")

    def test_set_for_exports_without_gst(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict(is_export_with_gst=False)
        sub.set_for_exports(invoice)
        self.assertEqual(invoice.invoice_sub_category, "Export Without Payment of Tax")
        self.assertEqual(invoice.invoice_type, "WOPAY")

    def test_set_for_b2cs(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict()
        sub.set_for_b2cs(invoice)
        self.assertEqual(invoice.invoice_sub_category, "B2C (Others)")

    def test_set_for_nil_exp_non_gst_registered_inter(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict(
            billing_address_gstin="24ABCDE1234",
            place_of_supply="06-Delhi",
            gst_category="Registered",
            company_gstin="24AAQCA8719H1ZC",
        )
        sub.set_for_nil_exp_non_gst(invoice)
        self.assertEqual(invoice.invoice_type, "Inter-State supplies to registered persons")
        self.assertEqual(invoice.invoice_sub_category, "Nil-Rated, Exempted, Non-GST")

    def test_set_for_nil_exp_non_gst_unregistered_intra(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict(
            billing_address_gstin="",
            place_of_supply="24-Gujarat",
            company_gstin="24AAQCA8719H1ZC",
        )
        sub.set_for_nil_exp_non_gst(invoice)
        self.assertEqual(invoice.invoice_type, "Intra-State supplies to unregistered persons")
        self.assertEqual(invoice.invoice_sub_category, "Nil-Rated, Exempted, Non-GST")

    def test_set_for_cdnr(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict(
            gst_category="Registered",
            is_reverse_charge=False,
        )
        sub.set_for_cdnr(invoice)
        self.assertEqual(invoice.invoice_sub_category, "Credit/Debit Notes (Registered)")

    def test_set_for_cdnur_export_with_gst(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict(
            is_export_with_gst=True,
            place_of_supply="96-Other Countries",
            gst_category="Overseas",
            company_gstin="24AAQCA8719H1ZC",
        )
        sub.set_for_cdnur(invoice)
        self.assertEqual(invoice.invoice_sub_category, "Credit/Debit Notes (Unregistered)")
        self.assertEqual(invoice.invoice_type, "EXPWP")

    def test_set_for_cdnur_export_without_gst(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict(
            is_export_with_gst=False,
            place_of_supply="96-Other Countries",
            gst_category="Overseas",
            company_gstin="24AAQCA8719H1ZC",
        )
        sub.set_for_cdnur(invoice)
        self.assertEqual(invoice.invoice_sub_category, "Credit/Debit Notes (Unregistered)")
        self.assertEqual(invoice.invoice_type, "EXPWOP")

    def test_set_for_cdnur_b2cl(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict(
            place_of_supply="06-Delhi",
            gst_category="Unregistered",
            company_gstin="24AAQCA8719H1ZC",
        )
        sub.set_for_cdnur(invoice)
        self.assertEqual(invoice.invoice_sub_category, "Credit/Debit Notes (Unregistered)")
        self.assertEqual(invoice.invoice_type, "B2CL")

    def test_set_for_ecommerce_supply_type_rc(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict(is_reverse_charge=True)
        sub.set_for_ecommerce_supply_type(invoice)
        self.assertEqual(invoice.ecommerce_supply_type, "Liable to pay tax u/s 9(5)")

    def test_set_for_ecommerce_supply_type_no_rc(self):
        sub = GSTR1Subcategory()
        invoice = frappe._dict(is_reverse_charge=False)
        sub.set_for_ecommerce_supply_type(invoice)
        self.assertEqual(invoice.ecommerce_supply_type, "Liable to collect tax u/s 52(TCS)")


class TestGSTR1DocumentIssuedSummary(IntegrationTestCase):
    def test_is_same_naming_series_consecutive_numbers(self):
        summary = GSTR1DocumentIssuedSummary(frappe._dict())
        self.assertTrue(summary.is_same_naming_series("SINV-00001", "SINV-00002"))

    def test_is_same_naming_series_different_alphabets(self):
        summary = GSTR1DocumentIssuedSummary(frappe._dict())
        self.assertFalse(summary.is_same_naming_series("SINV-00001", "PINV-00002"))

    def test_is_same_naming_series_different_length_numbers(self):
        summary = GSTR1DocumentIssuedSummary(frappe._dict())
        self.assertFalse(summary.is_same_naming_series("SINV-001", "SINV-0002"))

    def test_is_same_naming_series_non_consecutive(self):
        summary = GSTR1DocumentIssuedSummary(frappe._dict())
        self.assertFalse(summary.is_same_naming_series("SINV-00001", "SINV-00003"))

    def test_is_same_naming_series_with_common_suffix(self):
        summary = GSTR1DocumentIssuedSummary(frappe._dict())
        self.assertTrue(summary.is_same_naming_series("SINV-00001-2023", "SINV-00002-2023"))

    def test_is_same_naming_series_with_different_suffix(self):
        summary = GSTR1DocumentIssuedSummary(frappe._dict())
        self.assertFalse(summary.is_same_naming_series("SINV-00001-2023", "SINV-00002-2024"))

    def test_handle_amended_docs_moves_to_end(self):
        summary = GSTR1DocumentIssuedSummary(frappe._dict())
        doc1 = frappe._dict(name="SINV-00001", amended_from=None)
        doc2 = frappe._dict(name="SINV-00001-1", amended_from="SINV-00001")
        doc3 = frappe._dict(name="SINV-00002", amended_from=None)

        result = summary.handle_amended_docs([doc1, doc2, doc3])
        names = [d.name for d in result]
        self.assertEqual(names, ["SINV-00001", "SINV-00002", "SINV-00001-1"])

    def test_handle_amended_docs_no_amendments(self):
        summary = GSTR1DocumentIssuedSummary(frappe._dict())
        doc1 = frappe._dict(name="SINV-00001", amended_from=None)
        doc2 = frappe._dict(name="SINV-00002", amended_from=None)

        result = summary.handle_amended_docs([doc1, doc2])
        self.assertEqual(len(result), 2)

    def test_seperate_data_by_naming_series_basic_grouping(self):
        summary = GSTR1DocumentIssuedSummary(frappe._dict())
        data = [
            frappe._dict(name="SINV-00001", naming_series="SINV-", docstatus=1),
            frappe._dict(name="SINV-00002", naming_series="SINV-", docstatus=1),
            frappe._dict(name="PINV-00001", naming_series="PINV-", docstatus=1),
        ]
        result = summary.seperate_data_by_naming_series(data, "Invoices for outward supply")
        self.assertEqual(len(result), 2)
        sinv_entry = next(r for r in result if r["naming_series"] == "SINV-")
        self.assertEqual(sinv_entry["from_serial_no"], "SINV-00001")
        self.assertEqual(sinv_entry["to_serial_no"], "SINV-00002")
        self.assertEqual(sinv_entry["total_submitted"], 2)

    def test_seperate_data_by_naming_series_empty_data(self):
        summary = GSTR1DocumentIssuedSummary(frappe._dict())
        result = summary.seperate_data_by_naming_series([], "Test")
        self.assertEqual(result, [])

    def test_seperate_data_by_naming_series_with_draft_and_cancelled(self):
        summary = GSTR1DocumentIssuedSummary(frappe._dict())
        data = [
            frappe._dict(name="SINV-00001", naming_series="SINV-", docstatus=0),
            frappe._dict(name="SINV-00002", naming_series="SINV-", docstatus=1),
            frappe._dict(name="SINV-00003", naming_series="SINV-", docstatus=2),
        ]
        result = summary.seperate_data_by_naming_series(data, "Test")
        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry["total_draft"], 1)
        self.assertEqual(entry["total_submitted"], 1)
        self.assertEqual(entry["cancelled"], 1)
        self.assertEqual(entry["total_issued"], 3)


class TestGSTR11A11BData(IntegrationTestCase):
    def test_get_data_advances_type(self):
        filters = frappe._dict(type_of_business="Advances")
        gst_accounts = frappe._dict(
            igst_account="IGST",
            cgst_account="CGST",
            sgst_account="SGST",
            cess_account="CESS",
        )
        data = GSTR11A11BData(filters, gst_accounts)
        self.assertEqual(data.filters.type_of_business, "Advances")

    def test_get_data_adjustment_type(self):
        filters = frappe._dict(type_of_business="Adjustment")
        gst_accounts = frappe._dict(
            igst_account="IGST",
            cgst_account="CGST",
            sgst_account="SGST",
            cess_account="CESS",
        )
        data = GSTR11A11BData(filters, gst_accounts)
        self.assertEqual(data.filters.type_of_business, "Adjustment")

    def test_process_data_empty(self):
        filters = frappe._dict(type_of_business="Advances")
        gst_accounts = frappe._dict(
            igst_account="IGST",
            cgst_account="CGST",
            sgst_account="SGST",
            cess_account="CESS",
        )
        data = GSTR11A11BData(filters, gst_accounts)
        result = data.process_data([])
        self.assertEqual(result, {})

    def test_process_data_aggregation(self):
        filters = frappe._dict(type_of_business="Advances")
        gst_accounts = frappe._dict(
            igst_account="IGST",
            cgst_account="CGST",
            sgst_account="SGST",
            cess_account="CESS",
        )
        data = GSTR11A11BData(filters, gst_accounts)
        records = [
            frappe._dict(place_of_supply="06-Delhi", taxable_value=1000, tax_amount=180, cess_amount=10),
            frappe._dict(place_of_supply="06-Delhi", taxable_value=500, tax_amount=90, cess_amount=5),
        ]
        result = data.process_data(records)
        self.assertIn(("06-Delhi", 18), result)
        self.assertEqual(result[("06-Delhi", 18)][0], 1500)
        self.assertEqual(result[("06-Delhi", 18)][1], 15)

    def test_process_data_zero_taxable_value(self):
        filters = frappe._dict(type_of_business="Advances")
        gst_accounts = frappe._dict(
            igst_account="IGST",
            cgst_account="CGST",
            sgst_account="SGST",
            cess_account="CESS",
        )
        data = GSTR11A11BData(filters, gst_accounts)
        records = [
            frappe._dict(place_of_supply="06-Delhi", taxable_value=0, tax_amount=0, cess_amount=0),
        ]
        result = data.process_data(records)
        self.assertIn(("06-Delhi", 0), result)
        self.assertEqual(result[("06-Delhi", 0)][0], 0)
