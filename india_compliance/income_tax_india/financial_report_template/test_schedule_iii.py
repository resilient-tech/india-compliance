# Copyright (c) 2026, resilient tech and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.doctype.financial_report_template.financial_report_engine import FinancialReportEngine
from erpnext.accounts.utils import get_fiscal_year
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from india_compliance.gst_india.utils.tests import create_purchase_invoice, create_sales_invoice
from india_compliance.tests.erpnext_test_utils import (
    create_account as _create_account,
)
from india_compliance.tests.erpnext_test_utils import (
    create_and_submit_transaction_deletion_doc,
    make_journal_entry,
)

CHANGES_IN_INVENTORIES = "3. Changes in Inventories of Finished Goods, Work-in-Progress and Stock-in-Trade"
VARIANCE = "VARIANCE (Calculated vs Actual)"


class TestScheduleIIITemplates(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_schedule_iii")
        cls.company = "_Test Indian Registered Company"
        cls.test_date = today()
        cls.cost_center = frappe.get_value("Company", cls.company, "cost_center")

        cls.cash_account = frappe.get_value(
            "Account", {"company": cls.company, "account_type": "Cash", "is_group": 0}, "name"
        )
        if not cls.cash_account:
            cls.cash_account = frappe.get_value(
                "Account", {"company": cls.company, "account_name": ["like", "Cash%"], "is_group": 0}, "name"
            )

        create_and_submit_transaction_deletion_doc(cls.company)

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_schedule_iii")

    def execute_report(self, template_name):
        fiscal_year = get_fiscal_year(self.test_date, as_dict=True)
        filters = frappe._dict(
            {
                "company": self.company,
                "report_template": template_name,
                "filter_based_on": "Date Range",
                "period_start_date": self.test_date,
                "period_end_date": self.test_date,
                "from_fiscal_year": fiscal_year.name,
                "to_fiscal_year": fiscal_year.name,
                "periodicity": "Yearly",
                "accumulated_values": 0,
            }
        )
        _, data, _, _ = FinancialReportEngine().execute(filters)
        return data

    def get_row_total(self, data, account_name):
        for row in data:
            if row.get("account_name") == account_name:
                return row.get("total")

        return None

    def get_account(self, account_name):
        return frappe.get_value(
            "Account", {"account_name": account_name, "company": self.company, "is_group": 0}, "name"
        )

    def create_account(
        self, account_name, parent_account_name, root_type, account_category=None, account_type=None
    ):
        parent_account = frappe.get_value(
            "Account", {"company": self.company, "account_name": parent_account_name, "is_group": 1}, "name"
        )

        account_name = _create_account(
            account_name=account_name,
            parent_account=parent_account,
            company=self.company,
            account_type=account_type,
            is_group=0,
        )

        account = frappe.get_doc("Account", account_name)
        account.root_type = root_type
        account.account_category = account_category
        account.account_type = account_type
        account.save(ignore_permissions=True)

        return account.name

    def test_profit_and_loss_schedule_iii(self):
        """
        Tests P&L (Schedule III) aggregation.

        - Category based filtering (Revenue, Finance Costs)
        - Pattern based filtering (Employee Benefits, Other Expenses)
        - Account Type filtering (Depreciation)
        """
        # 1. Setup Accounts
        rev_acc = self.get_account("Sales")
        other_inc_acc = self.get_account("Gain/Loss on Asset Disposal")

        # Employee Benefits (Pattern matching: name contains Salary/Employee etc inside Operating Expenses)
        # NOTE: User pattern is "Employee", "Salary", "Wages", "Staff", "Gratuity", "Provident Fund", "Bonus"
        emp_acc = self.get_account("Salary")

        # Other Expenses (Pattern matching: name DOES NOT contain those strings)
        other_exp_acc = self.get_account("Office Rent")

        # Finance Costs
        finance_acc = self.get_account("Bank Charges")

        # Depreciation (Account Type based)
        dep_acc = self.get_account("Depreciation")

        # Tax Expense
        tax_acc = self.get_account("Tax Expense")
        def_tax_acc = self.create_account(
            "Deferred Tax Provision Test", "Indirect Expenses", "Expense", "Deferred Tax Expense"
        )

        # 2. Post Journal Entries
        cash = self.cash_account
        args = {
            "company": self.company,
            "cost_center": self.cost_center,
            "posting_date": self.test_date,
            "submit": True,
        }

        # Revenue
        make_journal_entry(rev_acc, cash, 10000, **args)
        make_journal_entry(other_inc_acc, cash, 2000, **args)

        # Expenses
        make_journal_entry(cash, emp_acc, 3000, **args)
        make_journal_entry(cash, other_exp_acc, 1000, **args)
        make_journal_entry(cash, finance_acc, 500, **args)

        make_journal_entry(cash, dep_acc, 800, **args, voucher_type="Depreciation Entry")
        make_journal_entry(cash, tax_acc, 400, **args)
        make_journal_entry(cash, def_tax_acc, 100, **args)

        # 3. Fetch Report
        data = self.execute_report("Standard Profit and Loss (Schedule III)")

        # 4. Assertions
        self.assertEqual(self.get_row_total(data, "I. Revenue from Operations"), -10000)
        self.assertEqual(self.get_row_total(data, "II. Other Income"), -2000)
        self.assertEqual(self.get_row_total(data, "III. Total Revenue (I + II)"), -12000)

        self.assertEqual(self.get_row_total(data, "4. Employee Benefits Expense"), -3000)
        self.assertEqual(self.get_row_total(data, "5. Finance Costs"), -500)
        self.assertEqual(self.get_row_total(data, "6. Depreciation and Amortization Expense"), -800)
        self.assertEqual(self.get_row_total(data, "7. Other Expenses"), -1000)

        self.assertEqual(self.get_row_total(data, "1. Current Tax"), -400)
        self.assertEqual(self.get_row_total(data, "2. Deferred Tax"), -100)
        self.assertEqual(self.get_row_total(data, "X. Tax Expense"), -500)

        # PROFIT_FOR_PERIOD = TOTAL_REVENUE - TOTAL_EXPENSES - TOTAL_TAX
        # TOTAL_EXPENSES = 3000+500+800+1000 = 5300
        self.assertEqual(self.get_row_total(data, "XV. Profit (Loss) for the Period (XI + XIV)"), -6200)

    def test_profit_and_loss_schedule_iii_stock_lines(self):
        """
        Tests the stock lines of P&L (Schedule III) under perpetual inventory.

        ERPNext cannot split raw material from stock-in-trade in the GL: consumption moves
        value stock-to-stock and every warehouse account is just "Stock Assets". So:

        - Cost of Materials Consumed carries no value
        - Changes in Inventories is the period's stock movement, sign reversed
        - Purchases of Stock-in-Trade is back-solved as COGS - Changes in Inventories
        - the two together equal COGS as booked, so the statement ties to the GL

        Expenses are debits, so they come out positive (the report is run with accumulated
        values off, the P&L report's default).
        """
        # opening stock: 10 x 100 received before the report period
        create_purchase_invoice(
            update_stock=1, set_posting_time=1, posting_date=add_days(self.test_date, -1), qty=10, rate=100
        )
        # purchases in the period: 5 x 100
        create_purchase_invoice(update_stock=1, qty=5, rate=100)
        # sale in the period: 8 units at valuation 100 -> COGS 800, closing stock 700
        create_sales_invoice(update_stock=1, qty=8, rate=150)

        data = self.execute_report("Standard Profit and Loss (Schedule III)")

        # raw material cannot be valued separately from stock-in-trade, so the line stays empty
        self.assertEqual(self.get_row_total(data, "1. Cost of Materials Consumed"), 0)

        # stock was drawn down from 1000 to 700, and a drawdown is an expense
        self.assertEqual(self.get_row_total(data, CHANGES_IN_INVENTORIES), 300)

        # COGS of 800 less the 300 drawn out of stock leaves the 500 purchased
        self.assertEqual(self.get_row_total(data, "2. Purchases of Stock in Trade"), 500)

        # the VARIANCE row hides itself only when the report ties back to the ledger
        self.assertIsNone(self.get_row_total(data, VARIANCE))

        # buy a further 10 x 100, so stock closes at 1700, above the opening 1000
        create_purchase_invoice(update_stock=1, qty=10, rate=100)

        data = self.execute_report("Standard Profit and Loss (Schedule III)")

        # the line flips sign once inventory is built up rather than drawn down
        self.assertEqual(self.get_row_total(data, CHANGES_IN_INVENTORIES), -700)

        # back-solving still returns every rupee purchased during the period
        self.assertEqual(self.get_row_total(data, "2. Purchases of Stock in Trade"), 1500)

        self.assertIsNone(self.get_row_total(data, VARIANCE))

        # Accumulated Values is deliberately not asserted. ERPNext's engine folds the
        # opening balance into the period movement for every account, so a Stock Assets
        # movement becomes its closing balance and the two line items above come out
        # wrong. That is an ERPNext bug (it breaks the shipped Horizontal P&L and Cash
        # Flow templates too) and must not be worked around here: the totals still tie,
        # and this template will be correct in both modes once the engine is fixed.

    def test_balance_sheet_schedule_iii(self):
        """
        Tests Balance Sheet (Schedule III) aggregation for new India-specific categories.

        - CWIP, DTA, DTL, Share App Money, etc.
        """
        # 1. Setup Accounts
        cwip_acc = self.create_account(
            "New Factory CWIP Test", "Fixed Assets", "Asset", "Capital Work in Progress"
        )
        dta_acc = self.create_account("DTA Account Test", "Fixed Assets", "Asset", "Deferred Tax Assets")
        dtl_acc = self.create_account(
            "DTL Account Test", "Non-Current Liabilities", "Liability", "Deferred Tax Liabilities"
        )
        loan_acc = self.create_account(
            "Security Deposit Test", "Loans and Advances (Assets)", "Asset", "Long-term Loans and Advances"
        )
        app_money_acc = self.create_account(
            "Application Money Test",
            "Current Liabilities",
            "Liability",
            "Share Application Money Pending Allotment",
        )
        warrants_acc = self.create_account(
            "Share Warrants Test", "Equity", "Equity", "Money Received Against Share Warrants"
        )

        # 2. Post Journal Entries (Simulate balances)
        cash = self.cash_account
        args = {
            "company": self.company,
            "cost_center": self.cost_center,
            "posting_date": self.test_date,
            "submit": True,
        }

        make_journal_entry(cwip_acc, cash, 50000, **args)
        make_journal_entry(dta_acc, cash, 5000, **args)
        make_journal_entry(cash, dtl_acc, 3000, **args)
        make_journal_entry(loan_acc, cash, 20000, **args)
        make_journal_entry(cash, app_money_acc, 15000, **args)
        make_journal_entry(cash, warrants_acc, 10000, **args)

        # 3. Fetch Report
        data = self.execute_report("Standard Balance Sheet (Schedule III)")

        # 4. Assertions
        self.assertEqual(self.get_row_total(data, "iii. Capital Work-in-Progress"), 50000)
        self.assertEqual(self.get_row_total(data, "c. Deferred Tax Assets (Net)"), 5000)
        self.assertEqual(self.get_row_total(data, "b. Deferred Tax Liabilities (Net)"), 3000)
        self.assertEqual(self.get_row_total(data, "d. Long-Term Loans and Advances"), 20000)
        self.assertEqual(self.get_row_total(data, "2. Share Application Money Pending Allotment"), 15000)
        self.assertEqual(self.get_row_total(data, "c. Money Received Against Share Warrants"), 10000)
