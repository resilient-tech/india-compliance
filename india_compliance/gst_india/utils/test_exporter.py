# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.utils.exporter import ExcelExporter


class TestExcelExporter(IntegrationTestCase):
    def test_insert_data_keeps_zero(self):
        """insert_data must write a numeric 0, not blank it out (regression: `value or ""`)."""
        excel = ExcelExporter()
        excel.wb.create_sheet("data")
        excel.insert_data(
            sheet_name="data",
            headers=[{"fieldname": "amount"}],
            data=[{"amount": 0}, {"amount": 100}],
        )

        ws = excel.wb["data"]
        self.assertEqual(ws.cell(row=1, column=1).value, 0)
        self.assertEqual(ws.cell(row=2, column=1).value, 100)
