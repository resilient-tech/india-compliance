# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from india_compliance.gst_india.utils.tests import create_purchase_invoice
from india_compliance.income_tax_india.overrides.company import TDS_ACCOUNT_NAME, create_tds_account
from india_compliance.income_tax_india.overrides.test_tax_withholding_category import (
    ABBR,
    COMPANY,
    create_supplier,
    create_tax_withholding_category,
    generate_unique_pan,
)
from india_compliance.income_tax_india.report.tds_computation_summary_india.tds_computation_summary_india import (
    execute,
)

TDS_ACCOUNT = f"{TDS_ACCOUNT_NAME} - {ABBR}"


class TestTdsComputationSummaryIndia(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_tds_account(COMPANY)
        cls.category = create_tax_withholding_category(
            "Test 194J TCS Report Category",
            TDS_ACCOUNT,
            tds_section="194J",
            old_income_tax_section="194J-OLD",
            entity_type="Individual",
            tax_withholding_rate=10,
        )
        cls.supplier = create_supplier("_Test TCS 194J Supplier", pan=generate_unique_pan())
        frappe.db.set_value("Supplier", cls.supplier, "tax_withholding_category", cls.category.name)

        cls.pi1 = create_purchase_invoice(
            supplier=cls.supplier,
            company=COMPANY,
            apply_tds=1,
            rate=50000,
            do_not_submit=1,
        )
        cls.pi1.submit()

        cls.pi2 = create_purchase_invoice(
            supplier=cls.supplier,
            company=COMPANY,
            apply_tds=1,
            rate=50000,
            do_not_submit=1,
        )
        cls.pi2.submit()

        cls.filters = frappe._dict(
            company=COMPANY,
            party_type="Supplier",
            from_date=today(),
            to_date=today(),
        )

    def test_additional_column_and_data_in_row(self):
        columns, data = execute(self.filters)
        fieldnames = [c.get("fieldname") for c in columns]
        self.assertIn("tds_section", fieldnames)
        self.assertIn("old_income_tax_section", fieldnames)
        supplier_category_row = next(
            (
                row
                for row in data
                if row.get("party") == self.supplier
                and row.get("tax_withholding_category") == self.category.name
            ),
            None,
        )
        self.assertIsNotNone(supplier_category_row)
        self.assertEqual(supplier_category_row.get("tds_section"), "194J")
        self.assertEqual(supplier_category_row.get("old_income_tax_section"), "194J-OLD")
        self.assertEqual(supplier_category_row.get("entity_type"), "Individual")
