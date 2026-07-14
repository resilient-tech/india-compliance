# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from india_compliance.income_tax_india.utils.msme import get_financial_year_dates


class IndiaMSMEClassification(Document):
    """A classification is resolved by date, so a row without a period is
    invisible to every lookup.

    Frappe does not run document hooks on child rows, so ``set_period`` cannot
    self-apply - every writer must call it. The parent does so on validate; the
    annual roll-forward, which uses ``db_insert``, calls it directly.
    """

    def set_period(self):
        if not self.financial_year:
            return

        self.from_date, self.to_date = get_financial_year_dates(self.financial_year)
