import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from india_compliance.gst_india.doctype.gst_settings.test_gst_settings import (
    update_gst_account,
)
from india_compliance.tests.erpnext_test_utils import create_account

COMPANY = "_Test Indian Registered Company"


class TestPeriodClosingVoucher(IntegrationTestCase):
    def setUp(self):
        fiscal_year, start_date, end_date = get_fiscal_year(getdate(), company=COMPANY)
        self.period_closing_voucher = frappe.get_doc(
            {
                "doctype": "Period Closing Voucher",
                "company": COMPANY,
                "fiscal_year": fiscal_year,
                "period_start_date": start_date,
                "period_end_date": end_date,
                "closing_account_head": "Retained Earnings - _TIRC",
                "transaction_date": getdate(),
                "remarks": "Test Period Closing Voucher",
            }
        )

    def test_period_closing_with_valid_gst_accounts(self):
        self.period_closing_voucher.insert()

        self.assertEqual(self.period_closing_voucher.docstatus, 0)

    def test_period_closing_with_gst_account_as_expense_account(self):
        # GST Account under an Expense group (as reported by users)
        expense_account = create_account(
            account_name="Test Output Tax CGST",
            account_type="Tax",
            company=COMPANY,
            parent_account="Indirect Expenses - _TIRC",
        )

        gst_settings = update_gst_account(COMPANY, "Output", cgst_account=expense_account)

        # such GST Accounts were configured before GST Settings validated Root Type
        gst_settings.flags.ignore_validate = True
        gst_settings.save()
        self.addCleanup(frappe.db.rollback)

        # Accounts are thrown as a list, so the message is the list of Accounts
        self.assertRaisesRegex(
            frappe.ValidationError,
            expense_account,
            self.period_closing_voucher.insert,
        )
