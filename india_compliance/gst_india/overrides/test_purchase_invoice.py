import re

import frappe
from frappe.tests import IntegrationTestCase, change_settings
from erpnext.accounts.doctype.account.test_account import create_account

from india_compliance.gst_india.utils.itc_claim import (
    ITC_CLAIM_PERIOD_DEFERRED,
    _validate_period_format,
    format_period,
)
from india_compliance.gst_india.utils.tests import append_item, create_purchase_invoice


class TestPurchaseInvoice(IntegrationTestCase):
    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_itc_classification(self):
        pinv = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            do_not_submit=1,
            item_code="_Test Service Item",
        )
        self.assertEqual(pinv.itc_classification, "Import Of Service")

        append_item(pinv)
        pinv.save()
        self.assertEqual(pinv.itc_classification, "Import Of Goods")

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

        frappe.db.set_value(
            "Company", company, "unrealized_profit_loss_account", account
        )
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

    def test_validate_invoice_length(self):
        # No error for registered supplier
        pinv = create_purchase_invoice(
            supplier="_Test Registered Supplier",
            is_reverse_charge=True,
            do_not_save=True,
        )
        setattr(pinv, "__newname", "INV/2022/00001/asdfsadf")  # NOQA
        pinv.meta.autoname = "prompt"
        pinv.save()

        # Error for unregistered supplier
        pinv = create_purchase_invoice(
            supplier="_Test Unregistered Supplier",
            is_reverse_charge=True,
            do_not_save=True,
        )
        setattr(pinv, "__newname", "INV/2022/00001/asdfsadg")  # NOQA
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
        Test that invalid period formats are rejected
        """
        # Test invalid formats
        invalid_periods = [
            "1320",  # Too short (only 4 digits)
            "132024",  # Month > 12
            "002024",  # Month = 00
            "12-2024",  # Wrong separator
            "Dec2024",  # Text format
            "MMYYYY",  # Literal text
            "abcdef",  # All text
            "12 2024",  # Space separator
        ]

        # Test at document level as well
        pinv = create_purchase_invoice(do_not_submit=True)
        pinv.itc_claim_period = invalid_periods[1]  # "132024"

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

        for invalid_period in invalid_periods:
            with self.assertRaisesRegex(
                frappe.exceptions.ValidationError,
                re.compile(r"ITC Claim Period '.*' must be in MMYYYY format"),
            ):
                _validate_period_format(invalid_period)

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
