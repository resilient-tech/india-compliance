# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from frappe.utils import add_days, getdate

from india_compliance.income_tax_india.constants import MSME_PAYMENT_DAYS
from india_compliance.income_tax_india.doctype.msme_registration.test_msme_registration import (
    FY,
    create_msme_registration,
    create_supplier,
)
from india_compliance.income_tax_india.report.msme_payables_due_within_45_days.msme_payables_due_within_45_days import (
    execute,
)
from india_compliance.income_tax_india.utils.test_msme_utils import COMPANY, MSMEReportTestCase

POSTING_DATE = "2023-05-01"
# posted 2023-05-01 -> due 2023-06-15; still within the 45 days as on 2023-06-01
AS_ON_DATE = "2023-06-01"


class TestMSMEPayablesDue(MSMEReportTestCase):
    def _run(self, supplier, as_on_date=AS_ON_DATE):
        _columns, data = execute({"company": COMPANY, "as_on_date": as_on_date, "supplier": supplier})
        return {row["voucher_no"]: row for row in data}

    def test_open_due_within_45_days_is_shown(self):
        supplier = self._create_msme_supplier(enterprise_type="Micro")
        pi = self._pi(supplier, POSTING_DATE, 5000)

        row = self._run(supplier)[pi.name]

        self.assertEqual(row["outstanding"], 5000)
        self.assertEqual(row["due_date"], getdate("2023-06-15"))
        self.assertEqual(row["days_remaining"], 14)  # 2023-06-01 -> 2023-06-15

    def test_overdue_is_excluded(self):
        """Once overdue it belongs to the 43B(h) disallowance report, not this one."""
        supplier = self._create_msme_supplier(enterprise_type="Micro")
        pi = self._pi(supplier, POSTING_DATE, 5000)

        overdue_on = add_days(POSTING_DATE, MSME_PAYMENT_DAYS + 1)
        self.assertNotIn(pi.name, self._run(supplier, as_on_date=overdue_on))

    def test_paid_due_is_excluded(self):
        supplier = self._create_msme_supplier(enterprise_type="Micro")
        pi = self._pi(supplier, POSTING_DATE, 5000)
        self._pay(pi, "2023-05-15")

        self.assertNotIn(pi.name, self._run(supplier))

    def test_trader_excluded(self):
        supplier = self._create_msme_supplier(enterprise_type="Micro", activity="Trading")
        pi = self._pi(supplier, POSTING_DATE, 5000)

        self.assertNotIn(pi.name, self._run(supplier))

    def test_medium_enterprise_excluded(self):
        supplier = self._create_msme_supplier(enterprise_type="Medium")
        pi = self._pi(supplier, POSTING_DATE, 5000)

        self.assertNotIn(pi.name, self._run(supplier))

    def test_cancelled_registration_excluded(self):
        """A supply accepted after cancellation is not from an MSME."""
        msme = create_msme_registration(
            registration_date="2023-04-01",
            classifications=[{"financial_year": FY, "enterprise_type": "Micro"}],
        )
        msme.mark_as_cancelled(add_days(POSTING_DATE, -1))

        supplier = create_supplier(msme.name)
        pi = self._pi(supplier, POSTING_DATE, 5000)

        self.assertNotIn(pi.name, self._run(supplier))

    def test_rows_are_sorted_most_urgent_first(self):
        supplier = self._create_msme_supplier(enterprise_type="Micro")
        # the later posting has the later due date, so it must sort second
        self._pi(supplier, POSTING_DATE, 1000)
        self._pi(supplier, add_days(POSTING_DATE, 10), 2000)

        _columns, data = execute({"company": COMPANY, "as_on_date": AS_ON_DATE, "supplier": supplier})

        due_dates = [row["due_date"] for row in data]
        self.assertEqual(due_dates, sorted(due_dates))
