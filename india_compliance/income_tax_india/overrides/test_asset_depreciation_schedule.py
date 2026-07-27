import frappe
from erpnext.accounts.utils import get_fiscal_year
from erpnext.assets.doctype.asset_depreciation_schedule.asset_depreciation_schedule import (
    get_asset_depr_schedule_doc,
)
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, date_diff, flt, getdate

from india_compliance.income_tax_india.overrides.asset_depreciation_schedule import (
    cancel_depreciation_entries,
    is_leap_year,
)

COMPANY = "_Test Indian Registered Company"
ABBR = "_TIRC"


class TestIsLeapYear(IntegrationTestCase):
    def test_divisible_by_400(self):
        self.assertTrue(is_leap_year(2000))

    def test_divisible_by_4_not_by_100(self):
        self.assertTrue(is_leap_year(2024))

    def test_not_divisible_by_4(self):
        self.assertFalse(is_leap_year(2023))

    def test_century_not_divisible_by_400(self):
        self.assertFalse(is_leap_year(2100))


class TestAssetDepreciationByIncomeTaxAct(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_asset_depr")
        cls.company = COMPANY
        cls._create_accounts()
        cls._create_finance_books()
        cls._create_asset_category()
        cls._create_item()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_asset_depr")

    @classmethod
    def _create_accounts(cls):
        fixed_asset_parent = frappe.db.get_value(
            "Account", {"account_name": "Fixed Assets", "company": cls.company, "is_group": 1}
        )

        cls.fixed_asset_acc = frappe.db.get_value(
            "Account", {"account_name": "Test IT Act Fixed Asset", "company": cls.company, "is_group": 0}
        )
        if not cls.fixed_asset_acc:
            doc = frappe.get_doc(
                {
                    "doctype": "Account",
                    "account_name": "Test IT Act Fixed Asset",
                    "parent_account": fixed_asset_parent,
                    "company": cls.company,
                    "account_type": "Fixed Asset",
                }
            ).insert()
            cls.fixed_asset_acc = doc.name

        cls.accum_depr_acc = frappe.db.get_value(
            "Account",
            {"account_name": "Test IT Act Accum Depr", "company": cls.company, "is_group": 0},
        )
        if not cls.accum_depr_acc:
            doc = frappe.get_doc(
                {
                    "doctype": "Account",
                    "account_name": "Test IT Act Accum Depr",
                    "parent_account": fixed_asset_parent,
                    "company": cls.company,
                    "account_type": "Accumulated Depreciation",
                }
            ).insert()
            cls.accum_depr_acc = doc.name

        cls.depr_exp_acc = frappe.db.get_value(
            "Account",
            {"account_name": "Test IT Act Depr Expense", "company": cls.company, "is_group": 0},
        )
        if not cls.depr_exp_acc:
            indirect_exp = frappe.db.get_value(
                "Account", {"account_name": "Indirect Expenses", "company": cls.company, "is_group": 1}
            )
            doc = frappe.get_doc(
                {
                    "doctype": "Account",
                    "account_name": "Test IT Act Depr Expense",
                    "parent_account": indirect_exp,
                    "company": cls.company,
                    "account_type": "Depreciation",
                }
            ).insert()
            cls.depr_exp_acc = doc.name

    @classmethod
    def _create_finance_books(cls):
        cls.fb_it = frappe.get_doc(
            {
                "doctype": "Finance Book",
                "finance_book_name": "_Test IT Act FB",
                "for_income_tax": 1,
            }
        ).insert(ignore_if_duplicate=True)

        cls.fb_regular = frappe.get_doc(
            {
                "doctype": "Finance Book",
                "finance_book_name": "_Test Regular FB",
                "for_income_tax": 0,
            }
        ).insert(ignore_if_duplicate=True)

    @classmethod
    def _create_asset_category(cls):
        cls.asset_category = frappe.get_doc(
            {
                "doctype": "Asset Category",
                "asset_category_name": "_Test IT Act Asset Category",
                "enable_cwip_accounting": 0,
                "accounts": [
                    {
                        "company_name": cls.company,
                        "fixed_asset_account": cls.fixed_asset_acc,
                        "accumulated_depreciation_account": cls.accum_depr_acc,
                        "depreciation_expense_account": cls.depr_exp_acc,
                    }
                ],
            }
        ).insert(ignore_if_duplicate=True)

    @classmethod
    def _create_item(cls):
        cls.item_code = "_Test IT Act Fixed Asset"
        if not frappe.db.exists("Item", cls.item_code):
            frappe.get_doc(
                {
                    "doctype": "Item",
                    "item_code": cls.item_code,
                    "item_group": "All Item Groups",
                    "is_stock_item": 0,
                    "is_fixed_asset": 1,
                    "asset_category": cls.asset_category.name,
                    "asset_naming_series": "ACC-ASS-.YYYY.-",
                    "item_defaults": [{"company": cls.company}],
                }
            ).insert()

    def _create_asset(self, available_for_use_date, finance_book=None, rate=15, frequency=12, daily_prorata=0, net_purchase=100000):
        suffix = frappe.generate_hash(length=6)
        fb_row = {
            "depreciation_start_date": available_for_use_date,
            "frequency_of_depreciation": frequency,
            "rate_of_depreciation": rate,
            "total_number_of_depreciations": 7,
            "daily_prorata_based": daily_prorata,
        }
        if finance_book:
            fb_row["finance_book"] = finance_book

        asset = frappe.get_doc(
            {
                "doctype": "Asset",
                "asset_name": f"_Test IT Act Asset {suffix}",
                "company": self.company,
                "item_code": self.item_code,
                "asset_category": self.asset_category.name,
                "net_purchase_amount": net_purchase,
                "gross_purchase_amount": net_purchase,
                "available_for_use_date": available_for_use_date,
                "finance_books": [fb_row],
            }
        )
        asset.insert()
        return asset

    def test_no_finance_book_uses_standard_wdv(self):
        asset = self._create_asset("2024-11-01")
        asset.submit()

        schedule = get_asset_depr_schedule_doc(asset.name, "Active")
        row = schedule.depreciation_schedule[0]
        self.assertEqual(flt(row.depreciation_amount, 2), 15000.0)

    def test_regular_finance_book_uses_standard_wdv(self):
        asset = self._create_asset("2024-11-01", finance_book=self.fb_regular.name)
        asset.submit()

        schedule = get_asset_depr_schedule_doc(asset.name, "Active", self.fb_regular.name)
        row = schedule.depreciation_schedule[0]
        self.assertEqual(flt(row.depreciation_amount, 2), 15000.0)

    def test_full_rate_when_used_over_180_days(self):
        asset = self._create_asset("2024-05-01", finance_book=self.fb_it.name)
        asset.submit()

        schedule = get_asset_depr_schedule_doc(asset.name, "Active", self.fb_it.name)
        row = schedule.depreciation_schedule[0]
        self.assertEqual(flt(row.depreciation_amount, 2), 15000.0)

    def test_half_rate_when_used_under_180_days(self):
        asset = self._create_asset("2024-11-01", finance_book=self.fb_it.name)
        asset.submit()

        schedule = get_asset_depr_schedule_doc(asset.name, "Active", self.fb_it.name)
        row = schedule.depreciation_schedule[0]
        self.assertEqual(flt(row.depreciation_amount, 2), 7500.0)

    def test_monthly_frequency_daily_prorata_half_rate(self):
        asset = self._create_asset(
            "2024-11-01", finance_book=self.fb_it.name, rate=15, frequency=1, daily_prorata=1
        )
        asset.submit()

        schedule = get_asset_depr_schedule_doc(asset.name, "Active", self.fb_it.name)
        first_row = schedule.depreciation_schedule[0]
        num_days = date_diff(
            add_days(get_fiscal_year("2024-11-01")[2], 1),
            "2024-11-01",
        )
        fraction = date_diff(first_row.schedule_date, add_days("2024-11-01", -1)) / num_days
        expected = flt(100000 * 7.5 / 100 * fraction)
        self.assertAlmostEqual(flt(first_row.depreciation_amount, 2), flt(expected, 2), places=1)

    def test_wdv_it_act_flag_set(self):
        asset = self._create_asset("2024-11-01", finance_book=self.fb_it.name)
        asset.submit()

        schedule = get_asset_depr_schedule_doc(asset.name, "Active", self.fb_it.name)
        self.assertTrue(schedule.flags.get("wdv_it_act_applied"))

    def test_cancel_depreciation_entries_skips_non_it_fb(self):
        asset = self._create_asset("2024-04-01", finance_book=self.fb_regular.name)
        asset.submit()

        try:
            cancel_depreciation_entries(asset, "2025-01-01")
        except Exception as e:
            self.fail(f"cancel_depreciation_entries raised unexpectedly: {e}")

    def test_cancel_depreciation_entries_handles_multiple_finance_books(self):
        suffix = frappe.generate_hash(length=6)
        fb_row_it = {
            "finance_book": self.fb_it.name,
            "depreciation_start_date": "2024-04-01",
            "frequency_of_depreciation": 12,
            "rate_of_depreciation": 15,
            "total_number_of_depreciations": 7,
            "daily_prorata_based": 0,
        }
        fb_row_regular = {
            "finance_book": self.fb_regular.name,
            "depreciation_start_date": "2024-04-01",
            "frequency_of_depreciation": 12,
            "rate_of_depreciation": 15,
            "total_number_of_depreciations": 7,
            "daily_prorata_based": 0,
        }

        asset = frappe.get_doc(
            {
                "doctype": "Asset",
                "asset_name": f"_Test Multi FB Asset {suffix}",
                "company": self.company,
                "item_code": self.item_code,
                "asset_category": self.asset_category.name,
                "net_purchase_amount": 100000,
                "gross_purchase_amount": 100000,
                "available_for_use_date": "2024-04-01",
                "finance_books": [fb_row_regular, fb_row_it],
            }
        )
        asset.insert()
        asset.submit()

        try:
            cancel_depreciation_entries(asset, "2025-03-31")
        except Exception as e:
            self.fail(f"cancel_depreciation_entries raised unexpectedly: {e}")

    def test_monthly_frequency_without_daily_prorata(self):
        asset = self._create_asset(
            "2024-04-01", finance_book=self.fb_it.name, rate=15, frequency=1, daily_prorata=0
        )
        asset.submit()

        schedule = get_asset_depr_schedule_doc(asset.name, "Active", self.fb_it.name)
        self.assertTrue(schedule.flags.get("wdv_it_act_applied"))
        self.assertGreater(schedule.depreciation_schedule[0].depreciation_amount, 0)

    def test_unsupported_frequency_raises_error(self):
        asset = self._create_asset(
            "2024-04-01", finance_book=self.fb_it.name, rate=15, frequency=6
        )
        with self.assertRaises(frappe.ValidationError):
            asset.submit()

    def test_second_year_depreciation_based_on_opening_wdv(self):
        asset = self._create_asset("2023-04-01", finance_book=self.fb_it.name, rate=15)
        asset.submit()

        schedule = get_asset_depr_schedule_doc(asset.name, "Active", self.fb_it.name)
        self.assertGreaterEqual(len(schedule.depreciation_schedule), 2)

        first_depr = schedule.depreciation_schedule[0].depreciation_amount
        second_depr = schedule.depreciation_schedule[1].depreciation_amount
        self.assertNotEqual(first_depr, second_depr)

        expected_wdv = 100000 - first_depr
        expected_second = flt(expected_wdv * 15 / 100)
        self.assertEqual(flt(second_depr, 2), flt(expected_second, 2))
