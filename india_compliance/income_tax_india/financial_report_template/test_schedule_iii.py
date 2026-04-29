# Copyright (c) 2026, resilient tech and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.doctype.financial_report_template.financial_report_engine import FinancialReportEngine
from erpnext.accounts.doctype.journal_entry.test_journal_entry import make_journal_entry
from erpnext.tests.utils import ERPNextTestSuite
from frappe.utils import today


class TestScheduleIIITemplates(ERPNextTestSuite):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = "_Test Company Schedule III"
        if not frappe.db.exists("Company", cls.company):
            from erpnext.setup.doctype.company.test_company import create_test_company

            create_test_company(company_name=cls.company)

        cls.cash_account = frappe.get_value(
            "Account", {"company": cls.company, "account_type": "Cash", "is_group": 0}, "name"
        )
        if not cls.cash_account:
            cls.cash_account = frappe.get_value(
                "Account", {"company": cls.company, "account_name": ["like", "Cash%"], "is_group": 0}, "name"
            )

        # Ensure India specific categories are synced
        from erpnext.accounts.doctype.financial_report_template.financial_report_template import (
            sync_templates,
        )

        sync_templates()

    def setUp(self):
        self.clear_gl_entries()

    def clear_gl_entries(self):
        frappe.db.delete("GL Entry", {"company": self.company})

    def create_account(
        self, account_name, parent_account_name, root_type, account_category=None, account_type=None
    ):
        name = f"{account_name} - {self.company}"
        if not frappe.db.exists("Account", name):
            parent_account = frappe.get_value(
                "Account", {"company": self.company, "account_name": parent_account_name}, "name"
            )
            if not parent_account:
                parent_account = frappe.db.get_value(
                    "Account", {"account_name": ["like", f"{parent_account_name}%"], "company": self.company}
                )

            account = frappe.get_doc(
                {
                    "doctype": "Account",
                    "account_name": account_name,
                    "parent_account": parent_account,
                    "company": self.company,
                    "root_type": root_type,
                    "account_category": account_category,
                    "account_type": account_type,
                }
            )
            account.insert()
        return name

    def test_profit_and_loss_schedule_iii(self):
        """
        Tests P&L (Schedule III) aggregation.

        - Category based filtering (Revenue, Finance Costs)
        - Pattern based filtering (Employee Benefits, Other Expenses)
        - Account Type filtering (Depreciation)
        """
        company = self.company
        # 1. Setup Accounts
        rev_acc = self.create_account(
            "Sales Revenue Test", "Direct Income", "Income", "Revenue from Operations"
        )
        other_inc_acc = self.create_account(
            "Dividend Income Test", "Indirect Income", "Income", "Other Operating Income"
        )

        # Employee Benefits (Pattern matching: name contains Salary/Employee etc inside Operating Expenses)
        # NOTE: User pattern is "Employee", "Salary", "Wages", "Staff", "Gratuity", "Provident Fund", "Bonus"
        emp_acc = self.create_account(
            "Staff Salary Test", "Operating Expenses", "Expense", "Operating Expenses"
        )

        # Other Expenses (Pattern matching: name DOES NOT contain those strings)
        other_exp_acc = self.create_account(
            "Rent Expense Test", "Operating Expenses", "Expense", "Operating Expenses"
        )

        # Finance Costs
        finance_acc = self.create_account(
            "Bank Interest Test", "Indirect Expense", "Expense", "Finance Costs"
        )

        # Depreciation (Account Type based)
        dep_acc = self.create_account(
            "Depreciation Account Test", "Indirect Expense", "Expense", None, "Depreciation"
        )

        # Tax Expense
        tax_acc = self.create_account(
            "Income Tax Provision Test", "Indirect Expense", "Expense", "Tax Expense"
        )
        def_tax_acc = self.create_account(
            "Deferred Tax Provision Test", "Indirect Expense", "Expense", "Deferred Tax Expense"
        )

        # 2. Post Journal Entries
        cash = self.cash_account

        # Revenue
        make_journal_entry(rev_acc, cash, 10000, company=company, posting_date=today(), submit=True)
        make_journal_entry(other_inc_acc, cash, 2000, company=company, posting_date=today(), submit=True)

        # Expenses
        make_journal_entry(cash, emp_acc, 3000, company=company, posting_date=today(), submit=True)
        make_journal_entry(cash, other_exp_acc, 1000, company=company, posting_date=today(), submit=True)
        make_journal_entry(cash, finance_acc, 500, company=company, posting_date=today(), submit=True)
        make_journal_entry(cash, dep_acc, 800, company=company, posting_date=today(), submit=True)
        make_journal_entry(cash, tax_acc, 400, company=company, posting_date=today(), submit=True)
        make_journal_entry(cash, def_tax_acc, 100, company=company, posting_date=today(), submit=True)

        # 3. Fetch Report
        template = frappe.get_doc("Financial Report Template", "Standard Profit and Loss (Schedule III)")
        engine = FinancialReportEngine(template)
        data = engine.execute({"company": company, "from_date": today(), "to_date": today()})

        # 4. Assertions
        results = {row["reference_code"]: row["amount"] for row in data if row.get("reference_code")}

        self.assertEqual(results.get("REV_OPERATIONS"), 10000)
        self.assertEqual(results.get("REV_OTHER"), 2000)
        self.assertEqual(results.get("TOTAL_REVENUE"), 12000)

        self.assertEqual(results.get("EXP_EMPLOYEE"), 3000)
        self.assertEqual(results.get("EXP_FINANCE"), 500)
        self.assertEqual(results.get("EXP_DEPRECIATION"), 800)
        self.assertEqual(results.get("EXP_OTHER"), 1000)

        self.assertEqual(results.get("TAX_CURRENT"), 400)
        self.assertEqual(results.get("TAX_DEFERRED"), 100)
        self.assertEqual(results.get("TOTAL_TAX"), 500)

        # PROFIT_FOR_PERIOD = TOTAL_REVENUE - TOTAL_EXPENSES - TOTAL_TAX
        # TOTAL_EXPENSES = 3000+500+800+1000 = 5300
        self.assertEqual(results.get("PROFIT_FOR_PERIOD"), 12000 - 5300 - 500)
        self.assertEqual(results.get("PROFIT_FOR_PERIOD"), 6200)

    def test_balance_sheet_schedule_iii(self):
        """
        Tests Balance Sheet (Schedule III) aggregation for new India-specific categories.

        - CWIP, DTA, DTL, Share App Money, etc.
        """
        company = self.company
        # 1. Setup Accounts
        cwip_acc = self.create_account(
            "New Factory CWIP Test", "Fixed Assets", "Asset", "Capital Work in Progress"
        )
        dta_acc = self.create_account("DTA Account Test", "Fixed Assets", "Asset", "Deferred Tax Assets")
        dtl_acc = self.create_account(
            "DTL Account Test", "Total Liabilities", "Liability", "Deferred Tax Liabilities"
        )
        loan_acc = self.create_account(
            "Security Deposit Test", "Fixed Assets", "Asset", "Long-term Loans and Advances"
        )
        app_money_acc = self.create_account(
            "Application Money Test",
            "Total Liabilities",
            "Liability",
            "Share Application Money Pending Allotment",
        )
        warrants_acc = self.create_account(
            "Share Warrants Test", "Equity", "Equity", "Money Received Against Share Warrants"
        )

        # 2. Post Journal Entries (Simulate balances)
        cash = self.cash_account

        make_journal_entry(cwip_acc, cash, 50000, company=company, posting_date=today(), submit=True)
        make_journal_entry(dta_acc, cash, 5000, company=company, posting_date=today(), submit=True)
        make_journal_entry(cash, dtl_acc, 3000, company=company, posting_date=today(), submit=True)
        make_journal_entry(loan_acc, cash, 20000, company=company, posting_date=today(), submit=True)
        make_journal_entry(cash, app_money_acc, 15000, company=company, posting_date=today(), submit=True)
        make_journal_entry(cash, warrants_acc, 10000, company=company, posting_date=today(), submit=True)

        # 3. Fetch Report
        template = frappe.get_doc("Financial Report Template", "Standard Balance Sheet (Schedule III)")
        engine = FinancialReportEngine(template)
        data = engine.execute({"company": company, "period_start_date": today(), "period_end_date": today()})

        # 4. Assertions
        results = {row["reference_code"]: row["amount"] for row in data if row.get("reference_code")}

        self.assertEqual(results.get("ASSET_CWIP"), 50000)
        self.assertEqual(results.get("ASSET_DTA"), 5000)
        self.assertEqual(results.get("LIAB_DTL"), 3000)
        self.assertEqual(results.get("ASSET_LOANS_ADV"), 20000)
        self.assertEqual(results.get("SHARE_APP_MONEY"), 15000)
        self.assertEqual(results.get("SF_MONEY_WARRANTS"), 10000)
