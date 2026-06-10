# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from frappe.utils import flt

from india_compliance.income_tax_india.report.msme_form_1.msme_form_1 import execute
from india_compliance.income_tax_india.utils.test_msme import COMPANY, MSMEReportTestCase


class TestMSMEForm1(MSMEReportTestCase):
    def _run_form1(self, group_by="Supplier Wise", period="Apr-Sep"):
        _columns, data = execute(
            {
                "company": COMPANY,
                "period_fy": "2023-2024",
                "period": period,
                "group_by": group_by,
            }
        )
        return data

    def test_invoice_wise_buckets(self):
        # Posted 2023-05-01 -> due 2023-06-15 (within Apr-Sep 2023).
        paid_on_time = self._pi(self.supplier, "2023-05-01", 4000)
        self._pay(paid_on_time, "2023-06-01")

        paid_late = self._pi(self.supplier, "2023-05-01", 5000)
        self._pay(paid_late, "2023-08-01")

        unpaid_overdue = self._pi(self.supplier, "2023-05-01", 7000)

        # Posted near period end -> still within 45 days as on 30 Sep.
        unpaid_recent = self._pi(self.supplier, "2023-09-15", 3000)

        rows = {
            row["voucher_no"]: row
            for row in self._run_form1(group_by="Invoice Wise")
            if row["supplier"] == self.supplier
        }

        self.assertEqual(flt(rows[paid_on_time.name]["paid_within_due"]), 4000)
        self.assertEqual(flt(rows[paid_late.name]["paid_after_due"]), 5000)
        self.assertEqual(flt(rows[unpaid_overdue.name]["outstanding_overdue"]), 7000)
        self.assertEqual(flt(rows[unpaid_recent.name]["outstanding_not_due"]), 3000)

    def test_supplier_wise_aggregates_with_counts(self):
        # Two invoices paid on time, one unpaid overdue -> aggregated per supplier
        # with a count (No.) and total amount per bucket, per the MCA annexure.
        # Dedicated supplier: aggregation must not mix sibling tests' invoices.
        supplier = self._create_msme_supplier(enterprise_type="Micro")
        for rate in (1000, 2000):
            pi = self._pi(supplier, "2023-05-01", rate)
            self._pay(pi, "2023-06-01")
        self._pi(supplier, "2023-05-01", 7000)

        rows = [row for row in self._run_form1() if row["supplier"] == supplier]
        self.assertEqual(len(rows), 1)

        row = rows[0]
        self.assertEqual(row["paid_within_due_count"], 2)
        self.assertEqual(flt(row["paid_within_due"]), 3000)
        self.assertEqual(row["outstanding_overdue_count"], 1)
        self.assertEqual(flt(row["outstanding_overdue"]), 7000)

    def test_medium_supplier_excluded_from_form1(self):
        medium = self._create_msme_supplier(enterprise_type="Medium")
        self._pi(medium, "2023-05-01", 9000)
        rows = [row for row in self._run_form1() if row["supplier"] == medium]
        self.assertEqual(rows, [])
