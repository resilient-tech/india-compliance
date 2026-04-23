# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from india_compliance.gst_india.utils.tests import create_purchase_invoice
from india_compliance.income_tax_india.overrides.test_tax_withholding_category import (
    ABBR,
    COMPANY,
    create_account,
    create_supplier,
    create_tax_withholding_category,
    generate_unique_pan,
)
from india_compliance.income_tax_india.report.tax_withholding_details_india.tax_withholding_details_india import (
    execute,
)

TDS_ACCOUNT = f"TDS Payable - {ABBR}"


class TestTaxWithholdingDetailsIndia(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_account(
            account_name="TDS Payable",
            parent_account=f"Duties and Taxes - {ABBR}",
            company=COMPANY,
        )
        cls.category = create_tax_withholding_category(
            "Test 194C TWD Report Category",
            TDS_ACCOUNT,
            tds_section="194C",
            old_income_tax_section="194C-OLD",
            entity_type="Individual",
            tax_withholding_rate=2,
        )
        cls.supplier = create_supplier("_Test TWD 194C Supplier", pan=generate_unique_pan())
        frappe.db.set_value("Supplier", cls.supplier, "tax_withholding_category", cls.category.name)

        cls.pi = create_purchase_invoice(
            supplier=cls.supplier,
            company=COMPANY,
            apply_tds=1,
            rate=50000,
            do_not_submit=1,
        )
        cls.pi.submit()

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

        invoice_row = next((row for row in data if row.get("ref_no") == self.pi.name), None)
        self.assertTrue(invoice_row)
        self.assertEqual(invoice_row.get("tds_section"), "194C")
        self.assertEqual(invoice_row.get("old_income_tax_section"), "194C-OLD")
        self.assertEqual(invoice_row.get("entity_type"), "Individual")
