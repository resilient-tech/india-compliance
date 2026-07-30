import frappe
from erpnext.assets.doctype.asset.depreciation import post_depreciation_entries, scrap_asset
from erpnext.assets.doctype.asset.mapper import make_sales_invoice
from erpnext.assets.doctype.asset_depreciation_schedule.asset_depreciation_schedule import (
    get_asset_depr_schedule_doc,
)
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, getdate

from india_compliance.tests.erpnext_test_utils import (
    create_account,
    create_asset,
    create_fiscal_year,
    set_depreciation_settings_in_company,
)

COMPANY = "_Test Indian Registered Company"
ABBR = "_TIRC"

COST = 100000
RATE = 15


class TestAssetDepreciationByIncomeTaxAct(IntegrationTestCase):
    """Depreciation as per the Income Tax Act, for a Finance Book with `for_income_tax` set.

    Both behaviours are regional overrides, see `hooks.py`:
    - `get_wdv_or_dd_depr_amount`: half rate in the first year if put to use for 180 days
      or less (s.32(1) proviso).
    - `cancel_depreciation_entries`: no depreciation in the financial year of sale/scrap.
    """

    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_asset_depr")
        cls.company = COMPANY
        cls.cost_center = f"Main - {ABBR}"

        cls._create_fiscal_years()
        cls._create_accounts()
        cls._create_location()
        cls._create_finance_books()
        cls._create_asset_category()
        cls._create_item()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_asset_depr")

    @classmethod
    def _create_fiscal_years(cls):
        # fixed dates, so the 180-day threshold stays verifiable against the Act
        for start_year in range(2022, 2027):
            create_fiscal_year(cls.company, f"{start_year}-04-01", f"{start_year + 1}-03-31")

    @classmethod
    def _create_accounts(cls):
        def parent(account_name):
            return frappe.db.get_value(
                "Account", {"account_name": account_name, "company": cls.company, "is_group": 1}
            )

        fixed_assets = parent("Fixed Assets")
        indirect_expenses = parent("Indirect Expenses")

        cls.fixed_asset_account = create_account(
            account_name="Test IT Act Fixed Asset",
            account_type="Fixed Asset",
            parent_account=fixed_assets,
            company=cls.company,
        )
        cls.accumulated_depreciation_account = create_account(
            account_name="Test IT Act Accumulated Depreciation",
            account_type="Accumulated Depreciation",
            parent_account=fixed_assets,
            company=cls.company,
        )
        cls.depreciation_expense_account = create_account(
            account_name="Test IT Act Depreciation Expense",
            account_type="Depreciation",
            parent_account=indirect_expenses,
            company=cls.company,
        )
        cls.disposal_account = create_account(
            account_name="Test IT Act Gain Loss on Asset Disposal",
            parent_account=indirect_expenses,
            company=cls.company,
        )

        set_depreciation_settings_in_company(
            cls.company,
            {
                "accumulated_depreciation_account": cls.accumulated_depreciation_account,
                "depreciation_expense_account": cls.depreciation_expense_account,
                "disposal_account": cls.disposal_account,
                "depreciation_cost_center": cls.cost_center,
            },
        )

    @classmethod
    def _create_location(cls):
        cls.location = "_Test IT Act Location"
        if not frappe.db.exists("Location", cls.location):
            frappe.get_doc({"doctype": "Location", "location_name": cls.location}).insert()

    @classmethod
    def _create_finance_books(cls):
        cls.fb_income_tax = frappe.get_doc(
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
                        "fixed_asset_account": cls.fixed_asset_account,
                        "accumulated_depreciation_account": cls.accumulated_depreciation_account,
                        "depreciation_expense_account": cls.depreciation_expense_account,
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
                    "gst_hsn_code": "84713010",
                    "is_stock_item": 0,
                    "is_fixed_asset": 1,
                    "asset_category": cls.asset_category.name,
                    "asset_naming_series": "ACC-ASS-.YYYY.-",
                }
            ).insert()

    def _create_asset(self, available_for_use_date, **args):
        args.setdefault("rate_of_depreciation", RATE)
        args.setdefault("frequency_of_depreciation", 12)
        args.setdefault("total_number_of_depreciations", 5)
        args.setdefault("depreciation_start_date", available_for_use_date)

        return create_asset(
            asset_name=f"_Test IT Act Asset {frappe.generate_hash(length=6)}",
            company=self.company,
            item_code=self.item_code,
            asset_category=self.asset_category.name,
            location=self.location,
            cost_center=self.cost_center,
            net_purchase_amount=COST,
            available_for_use_date=available_for_use_date,
            calculate_depreciation=1,
            submit=1,
            **args,
        )

    def _get_schedule(self, asset, finance_book=None):
        return get_asset_depr_schedule_doc(asset.name, "Active", finance_book)

    def _get_depreciation_amount(self, asset, finance_book=None, row_idx=0):
        schedule = self._get_schedule(asset, finance_book)
        return flt(schedule.depreciation_schedule[row_idx].depreciation_amount, 2)

    # get_wdv_or_dd_depr_amount

    def test_act_rate_is_not_applied_without_a_finance_book(self):
        """Only that the Act's rate was not applied; ERPNext's arithmetic is its own to test."""
        asset = self._create_asset("2024-05-01", depreciation_start_date="2025-03-31")

        self.assertNotEqual(self._get_depreciation_amount(asset), 15000)

    def test_act_rate_is_not_applied_for_a_non_income_tax_finance_book(self):
        asset = self._create_asset(
            "2024-11-01",
            depreciation_start_date="2025-03-31",
            finance_book=self.fb_regular.name,
        )

        # under 180 days in use, but the half rate is an Income Tax Act rule only
        self.assertNotEqual(self._get_depreciation_amount(asset, self.fb_regular.name), 7500)

    def test_full_rate_when_put_to_use_for_more_than_180_days(self):
        asset = self._create_asset(
            "2024-05-01",
            depreciation_start_date="2025-03-31",
            finance_book=self.fb_income_tax.name,
        )

        # 1-May-2024 to 31-Mar-2025 is 335 days, so the full 15% applies
        self.assertEqual(self._get_depreciation_amount(asset, self.fb_income_tax.name), 15000)

    def test_half_rate_when_put_to_use_for_less_than_180_days(self):
        asset = self._create_asset(
            "2024-11-01",
            depreciation_start_date="2025-03-31",
            finance_book=self.fb_income_tax.name,
        )

        # 1-Nov-2024 to 31-Mar-2025 is 151 days, so the rate is halved to 7.5%
        self.assertEqual(self._get_depreciation_amount(asset, self.fb_income_tax.name), 7500)

    def test_first_year_is_not_prorated_by_days_in_use(self):
        """The Act charges a half or full year, never a day-count fraction."""
        asset = self._create_asset(
            "2024-11-15",
            depreciation_start_date="2025-03-31",
            finance_book=self.fb_income_tax.name,
        )

        # not 7500 * 137/365, but exactly half rate
        self.assertEqual(self._get_depreciation_amount(asset, self.fb_income_tax.name), 7500)

    def test_second_year_applies_full_rate_to_opening_wdv(self):
        asset = self._create_asset(
            "2023-04-01",
            depreciation_start_date="2024-03-31",
            finance_book=self.fb_income_tax.name,
        )

        # first year on cost, second on the written down value
        self.assertEqual(self._get_depreciation_amount(asset, self.fb_income_tax.name), 15000)
        self.assertEqual(self._get_depreciation_amount(asset, self.fb_income_tax.name, row_idx=1), 12750)

    def test_yearly_daily_prorata_uses_366_days_in_a_leap_year(self):
        asset = self._create_asset(
            "2022-04-01",
            depreciation_start_date="2023-03-31",
            finance_book=self.fb_income_tax.name,
            daily_prorata_based=1,
        )

        # FY 2023-24 ends 31-Mar-2024 and contains 29-Feb, so 12750 is scaled by 366/365
        self.assertEqual(
            self._get_depreciation_amount(asset, self.fb_income_tax.name, row_idx=1),
            flt(12750 * 366 / 365, 2),
        )

    def test_monthly_depreciation_totals_the_annual_rate(self):
        asset = self._create_asset(
            "2024-04-01",
            depreciation_start_date="2024-04-30",
            finance_book=self.fb_income_tax.name,
            frequency_of_depreciation=1,
            total_number_of_depreciations=60,
        )

        # twelve monthly rows must add up to the annual rate
        self.assertEqual(self._get_first_year_total(asset, "2025-03-31"), 15000)

    def test_monthly_daily_prorata_depreciation_totals_the_annual_rate(self):
        asset = self._create_asset(
            "2024-04-01",
            depreciation_start_date="2024-04-30",
            finance_book=self.fb_income_tax.name,
            frequency_of_depreciation=1,
            total_number_of_depreciations=60,
            daily_prorata_based=1,
        )

        # each row is rounded to currency precision, so allow a paisa each
        self.assertAlmostEqual(self._get_first_year_total(asset, "2025-03-31"), 15000, delta=0.12)

    def _get_first_year_total(self, asset, fiscal_year_end):
        schedule = self._get_schedule(asset, self.fb_income_tax.name)
        return flt(
            sum(
                row.depreciation_amount
                for row in schedule.depreciation_schedule
                if getdate(row.schedule_date) <= getdate(fiscal_year_end)
            ),
            2,
        )

    def test_only_monthly_and_yearly_frequency_is_supported(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Only monthly and yearly"):
            self._create_asset(
                "2024-04-01",
                depreciation_start_date="2024-09-30",
                finance_book=self.fb_income_tax.name,
                frequency_of_depreciation=6,
                total_number_of_depreciations=10,
            )

    # cancel_depreciation_entries

    def _book_depreciation(self, asset, upto_date, finance_book=None):
        """Post real Depreciation Entries and return {schedule_date: journal_entry}."""
        post_depreciation_entries(date=upto_date)

        schedule = self._get_schedule(asset, finance_book)
        booked = {
            getdate(row.schedule_date): row.journal_entry
            for row in schedule.depreciation_schedule
            if row.journal_entry
        }
        self.assertTrue(booked, "No depreciation entry was booked, nothing to cancel")
        return booked

    def _assert_only_year_of_disposal_is_cancelled(self, booked):
        self.assertEqual(
            frappe.db.get_value("Journal Entry", booked[getdate("2025-03-31")], "docstatus"),
            1,
            "Depreciation of an earlier financial year must stay booked",
        )
        self.assertEqual(
            frappe.db.get_value("Journal Entry", booked[getdate("2026-03-31")], "docstatus"),
            2,
            "Depreciation of the financial year of disposal must be cancelled",
        )

    def test_depreciation_of_year_of_sale_is_cancelled(self):
        """Reaches the override through `Sales Invoice` -> `depreciate_asset`."""
        asset = self._create_asset(
            "2024-04-01",
            depreciation_start_date="2025-03-31",
            finance_book=self.fb_income_tax.name,
        )
        booked = self._book_depreciation(asset, "2026-03-31", self.fb_income_tax.name)

        invoice = make_sales_invoice(
            asset=asset.name,
            item_code=self.item_code,
            company=self.company,
            sell_qty=asset.asset_quantity,
        )
        invoice.customer = "_Test Registered Customer"
        invoice.set_posting_time = 1
        invoice.posting_date = invoice.due_date = "2026-03-31"
        invoice.items[0].rate = 50000
        invoice.insert()
        invoice.submit()

        self.assertEqual(frappe.db.get_value("Asset", asset.name, "status"), "Sold")
        self._assert_only_year_of_disposal_is_cancelled(booked)

    def test_only_income_tax_finance_book_is_cancelled_on_scrap(self):
        asset = self._create_asset(
            "2024-04-01",
            finance_books=[
                {"finance_book": self.fb_regular.name, "depreciation_start_date": "2025-03-31"},
                {"finance_book": self.fb_income_tax.name, "depreciation_start_date": "2025-03-31"},
            ],
        )
        regular = self._book_depreciation(asset, "2026-03-31", self.fb_regular.name)
        income_tax = self._book_depreciation(asset, "2026-03-31", self.fb_income_tax.name)

        scrap_asset(asset.name, "2026-03-31")

        self.assertEqual(
            frappe.db.get_value("Journal Entry", regular[getdate("2026-03-31")], "docstatus"),
            1,
            "The Income Tax Act rule must not touch a regular Finance Book",
        )
        self.assertEqual(
            frappe.db.get_value("Journal Entry", income_tax[getdate("2026-03-31")], "docstatus"),
            2,
            "Depreciation of the financial year of scrap must be cancelled",
        )
