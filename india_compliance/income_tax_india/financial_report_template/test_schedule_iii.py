# Copyright (c) 2026, resilient tech and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.doctype.financial_report_template.financial_report_engine import FinancialReportEngine
from erpnext.accounts.utils import get_fiscal_year
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from india_compliance.tests.erpnext_test_utils import (
    create_account as _create_account,
)
from india_compliance.tests.erpnext_test_utils import (
    create_and_submit_transaction_deletion_doc,
    make_journal_entry,
)


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
