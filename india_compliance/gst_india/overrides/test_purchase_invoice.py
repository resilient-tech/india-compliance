import re
import unittest.mock as mock

import frappe
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import add_months, getdate

from india_compliance.gst_india.utils.itc_claim import (
    ITC_CLAIM_PERIOD_DEFERRED,
    format_period,
    update_gstr3b_filing_status,
)
from india_compliance.gst_india.utils.tests import append_item, create_purchase_invoice

with mock.patch("frappe.db"), mock.patch("frappe.new_doc"), mock.patch("frappe.get_doc"):
    from erpnext.accounts.doctype.account.test_account import create_account


class TestPurchaseInvoice(IntegrationTestCase):
    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_boe_applicability_auto_set_without_gst_taxes(self):
        """Import Of Goods without GST taxes → is_boe_applicable auto-set to 1."""
        pinv = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            do_not_submit=1,
        )

        self.assertEqual(pinv.itc_classification, "Import Of Goods")
        self.assertEqual(pinv.is_boe_applicable, 1)
        self.assertEqual(pinv.items[0].pending_boe_qty, pinv.items[0].qty)

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_boe_applicability_auto_set_with_gst_taxes(self):
        """Import Of Goods (SEZ) with GST taxes → is_boe_applicable auto-set to 0."""
        # Use SEZ registered supplier: has GSTIN + itc_classification = Import Of Goods
        pinv = create_purchase_invoice(
            supplier="_Test Registered Supplier",
            do_not_save=1,
            do_not_submit=1,
            is_out_state=True,
        )
        pinv.gst_category = "SEZ"
        pinv.save()

        self.assertEqual(pinv.itc_classification, "Import Of Goods")
        self.assertEqual(pinv.is_boe_applicable, 0)
        self.assertEqual(pinv.items[0].pending_boe_qty, 0)

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_sez_goods_import_with_zero_gst_rates(self):
        """SEZ goods import should save even when GST tax rows exist with zero rates."""
        pinv = create_purchase_invoice(
            supplier="_Test Registered Supplier",
            do_not_save=1,
            do_not_submit=1,
            is_out_state=True,
        )
        pinv.gst_category = "SEZ"

        for tax in pinv.taxes:
            tax.rate = 0

        pinv.save()

        self.assertEqual(pinv.itc_classification, "Import Of Goods")
        self.assertEqual(pinv.items[0].gst_treatment, "Taxable")
        self.assertEqual(pinv.items[0].igst_rate, 0)

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_boe_applicability_auto_uncheck_when_not_import_of_goods(self):
        """is_boe_applicable should be 0 when itc_classification is not Import Of Goods."""
        pinv = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            item_code="_Test Service Item",
            do_not_submit=1,
        )
        # Service item → itc_classification = Import Of Service → is_boe_applicable auto-set to 0
        self.assertEqual(pinv.itc_classification, "Import Of Service")
        self.assertEqual(pinv.is_boe_applicable, 0)

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_itc_classification(self):
        pinv = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            do_not_submit=1,
            item_code="_Test Service Item",
        )
        self.assertEqual(pinv.itc_classification, "Import Of Service")
        self.assertEqual(pinv.items[0].gst_treatment, "Taxable")

        pinv = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            do_not_submit=1,
        )
        self.assertEqual(pinv.itc_classification, "Import Of Goods")
        self.assertEqual(pinv.items[0].gst_treatment, "Taxable")

        pinv = create_purchase_invoice(
            supplier="_Test Registered Supplier",
            do_not_submit=1,
            do_not_save=1,
        )
        pinv.gst_category = "SEZ"
        pinv.save()
        self.assertEqual(pinv.itc_classification, "Import Of Goods")
        self.assertEqual(pinv.items[0].gst_treatment, "Taxable")

        pinv = create_purchase_invoice(
            supplier="_Test Registered Supplier",
            do_not_submit=1,
            do_not_save=1,
            item_code="_Test Service Item",
        )
        pinv.gst_category = "SEZ"
        pinv.save()
        self.assertEqual(pinv.itc_classification, "All Other ITC")

        pinv = create_purchase_invoice(
            supplier="_Test Registered Supplier",
            is_reverse_charge=1,
            do_not_submit=1,
        )
        self.assertEqual(pinv.itc_classification, "ITC on Reverse Charge")

        pinv.is_reverse_charge = 0
        pinv.save()
        self.assertEqual(pinv.itc_classification, "All Other ITC")

        company = "_Test Indian Registered Company"
        account = create_account(
            account_name="Unrealized Profit",
            parent_account="Current Assets - _TIRC",
            company=company,
        )

        frappe.db.set_value("Company", company, "unrealized_profit_loss_account", account)
        pinv = create_purchase_invoice(
            supplier="Test Internal with ISD Supplier",
            qty=-1,
            is_return=1,
        )
        self.assertEqual(pinv.itc_classification, "Input Service Distributor")

        pinv = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            do_not_save=1,
            is_reverse_charge=1,
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            "Reverse Charge is not applicable on Import of Goods",
            pinv.save,
        )

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_service_and_goods_import_invoice_itc_classification(self):
        test_cases = (
            ("Overseas", "_Test Foreign Supplier"),
            ("SEZ", "_Test Registered Supplier"),
        )

        for gst_category, supplier in test_cases:
            pinv = create_purchase_invoice(
                supplier=supplier,
                do_not_submit=1,
                do_not_save=1,
                item_code="_Test Service Item",
            )
            pinv.gst_category = gst_category
            append_item(pinv)
            pinv.save()

            self.assertEqual(pinv.itc_classification, "Import Of Goods")
            self.assertEqual(len(pinv.items), 2)
            self.assertEqual(pinv.items[0].gst_treatment, "Taxable")
            self.assertEqual(pinv.items[1].gst_treatment, "Taxable")

    def test_validate_invoice_length(self):
        # No error for registered supplier
        pinv = create_purchase_invoice(
            supplier="_Test Registered Supplier",
            is_reverse_charge=True,
            do_not_save=True,
        )
        setattr(pinv, "__newname", "INV/2022/00001/asdfsadf")
        pinv.meta.autoname = "prompt"
        pinv.save()

        # Error for unregistered supplier
        pinv = create_purchase_invoice(
            supplier="_Test Unregistered Supplier",
            is_reverse_charge=True,
            do_not_save=True,
        )
        setattr(pinv, "__newname", "INV/2022/00001/asdfsadg")
        pinv.save()

        self.assertEqual(
            frappe.parse_json(frappe.message_log[-1]).get("message"),
            "Transaction Name must be 16 characters or fewer to meet GST requirements",
        )

        # Reset autoname (as it's cached)
        pinv.meta.autoname = "naming_series:"

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    @change_settings("GST Settings", {"validate_hsn_code": 0})
    def test_validate_hsn_code_for_overseas(self):
        frappe.db.set_value("Item", "_Test Service Item", "gst_hsn_code", "")
        pinv = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            do_not_submit=1,
            do_not_save=1,
            item_code="_Test Service Item",
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(GST HSN Code is mandatory for Overseas Purchase Invoice.*)"),
            pinv.save,
        )

        frappe.db.set_value("Item", "_Test Service Item", "gst_hsn_code", "999900")

    def test_itc_claim_period_invalid_format(self):
        """
        Test that invalid period formats are rejected at document level
        """
        pinv = create_purchase_invoice(do_not_submit=True)
        pinv.itc_claim_period = "132024"  # Invalid: Month > 12

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"ITC Claim Period '.*' must be in MMYYYY format"),
            pinv.save,
        )

        pinv.reload()
        pinv.itc_claim_period = ""
        pinv.submit()

        self.assertEqual(pinv.itc_claim_period, format_period(pinv.posting_date))

        pinv.itc_claim_period = ""
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"ITC Claim Period.*is a mandatory field"),
            pinv.save,
        )

    def test_itc_claim_period_for_unregistered_rcm(self):
        """
        For Unregistered supplier RCM, ITC Claim Period must match the posting period
        """
        pinv = create_purchase_invoice(
            supplier="_Test Unregistered Supplier",
            is_reverse_charge=True,
            do_not_submit=True,
        )

        posting_period = format_period(pinv.posting_date)
        self.assertEqual(pinv.itc_claim_period, posting_period)

        # Try to change itc_claim_period to a different period - should fail
        pinv.itc_claim_period = "012099"  # Different period

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(
                r"ITC Claim Period must be .* for purchases from Unregistered suppliers under Reverse Charge"
            ),
            pinv.save,
        )

        # Try to set to "Deferred" - should also fail for Unregistered RCM
        pinv.reload()
        pinv.itc_claim_period = ITC_CLAIM_PERIOD_DEFERRED

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(
                r"ITC Claim Period must be .* for purchases from Unregistered suppliers under Reverse Charge"
            ),
            pinv.save,
        )

    def test_itc_claim_period_deferred(self):
        """
        Test that 'Deferred' is a valid ITC Claim Period for regular invoices
        """
        pinv = create_purchase_invoice(do_not_submit=True)

        # Set to "Deferred" - should be valid
        pinv.itc_claim_period = ITC_CLAIM_PERIOD_DEFERRED
        pinv.save()

        self.assertEqual(pinv.itc_claim_period, ITC_CLAIM_PERIOD_DEFERRED)

        # Submit and verify it's still valid
        pinv.submit()
        self.assertEqual(pinv.itc_claim_period, ITC_CLAIM_PERIOD_DEFERRED)

    def test_itc_claim_period_update_restriction_when_filed(self):
        """
        Test that ITC Claim Period cannot be changed when GSTR-3B is filed
        """
        pinv = create_purchase_invoice(do_not_submit=True)
        current_period = format_period(pinv.posting_date)
        pinv.submit()

        self.assertEqual(pinv.itc_claim_period, current_period)

        posting_date = getdate(pinv.posting_date)
        month_or_quarter = posting_date.strftime("%B")
        year = posting_date.year

        # Mark GSTR-3B as filed for the current period
        update_gstr3b_filing_status(
            company_gstin=pinv.company_gstin,
            month_or_quarter=month_or_quarter,
            year=year,
            status="Filed",
        )

        # Try to change to a different period - should fail
        next_period = format_period(add_months(pinv.posting_date, 1))
        pinv.itc_claim_period = next_period

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"Cannot change ITC Claim Period from .* to .*\. GSTR-3B already filed for .*\."),
            pinv.save,
        )

        # Reload and try to change to "Deferred" - should also fail
        pinv.reload()
        pinv.itc_claim_period = ITC_CLAIM_PERIOD_DEFERRED

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"Cannot change ITC Claim Period from .* to .*\. GSTR-3B already filed for .*\."),
            pinv.save,
        )

        # Mark the current period as unfiled
        update_gstr3b_filing_status(
            company_gstin=pinv.company_gstin,
            month_or_quarter=month_or_quarter,
            year=year,
            status="Not Filed",
        )

        # Now it should be possible to change
        pinv.reload()
        pinv.itc_claim_period = ITC_CLAIM_PERIOD_DEFERRED
        pinv.save()

        self.assertEqual(pinv.itc_claim_period, ITC_CLAIM_PERIOD_DEFERRED)

    def test_itc_claim_period_change_unfiled_to_unfiled(self):
        """Change from one unfiled period to another — should be allowed."""
        pinv = create_purchase_invoice(do_not_submit=True)

        pinv.itc_claim_period = format_period(pinv.posting_date)
        pinv.save()

        next_period = format_period(add_months(pinv.posting_date, 1))
        pinv.itc_claim_period = next_period
        pinv.save()

        self.assertEqual(pinv.itc_claim_period, next_period)

    def test_itc_claim_period_change_deferred_to_unfiled(self):
        """Change from Deferred to a specific unfiled period — should be allowed."""
        pinv = create_purchase_invoice(do_not_submit=True)

        pinv.itc_claim_period = ITC_CLAIM_PERIOD_DEFERRED
        pinv.save()
        self.assertEqual(pinv.itc_claim_period, ITC_CLAIM_PERIOD_DEFERRED)

        unfiled_period = format_period(pinv.posting_date)
        pinv.itc_claim_period = unfiled_period
        pinv.save()

        self.assertEqual(pinv.itc_claim_period, unfiled_period)

    def test_itc_claim_period_change_to_filed_period_blocked(self):
        """Cannot change TO a filed period (even if current is unfiled)."""
        pinv = create_purchase_invoice(do_not_submit=True)
        pinv.submit()

        next_period = format_period(add_months(pinv.posting_date, 1))
        next_date = getdate(add_months(pinv.posting_date, 1))

        # File the *target* period
        update_gstr3b_filing_status(
            company_gstin=pinv.company_gstin,
            month_or_quarter=next_date.strftime("%B"),
            year=next_date.year,
            status="Filed",
        )

        pinv.itc_claim_period = next_period
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"GSTR-3B already filed"),
            pinv.save,
        )

        # cleanup
        update_gstr3b_filing_status(
            company_gstin=pinv.company_gstin,
            month_or_quarter=next_date.strftime("%B"),
            year=next_date.year,
            status="Not Filed",
        )

    def test_itc_claim_period_change_deferred_to_filed_blocked(self):
        """Cannot change from Deferred TO a filed period."""
        pinv = create_purchase_invoice(do_not_submit=True)
        pinv.itc_claim_period = ITC_CLAIM_PERIOD_DEFERRED
        pinv.submit()

        posting_date = getdate(pinv.posting_date)
        posting_period = format_period(posting_date)

        # File the target period
        update_gstr3b_filing_status(
            company_gstin=pinv.company_gstin,
            month_or_quarter=posting_date.strftime("%B"),
            year=posting_date.year,
            status="Filed",
        )

        pinv.itc_claim_period = posting_period
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"GSTR-3B already filed"),
            pinv.save,
        )

        # cleanup
        update_gstr3b_filing_status(
            company_gstin=pinv.company_gstin,
            month_or_quarter=posting_date.strftime("%B"),
            year=posting_date.year,
            status="Not Filed",
        )
