# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.report.tax_withholding_details.tax_withholding_details import (
    TaxWithholdingDetailsReport,
)
from frappe import _

TWC_INDIA_FIELDS = ("tds_section", "old_income_tax_section", "entity_type")


class TaxWithholdingDetailsIndiaReport(TaxWithholdingDetailsReport):
    def get_entries_query(self):
        twc = frappe.qb.DocType("Tax Withholding Category")
        query = super().get_entries_query()
        return (
            query.left_join(twc)
            .on(twc.name == frappe.qb.DocType("Tax Withholding Entry").tax_withholding_category)
            .select(twc.tds_section, twc.old_income_tax_section, twc.entity_type)
        )

    def get_india_columns(self):
        return [
            {
                "label": _("New Income Tax Section"),
                "fieldname": "tds_section",
                "fieldtype": "Data",
                "width": 120,
            },
            {
                "label": _("Old Income Tax Section"),
                "fieldname": "old_income_tax_section",
                "fieldtype": "Data",
                "width": 150,
            },
            {
                "label": _("Entity Type"),
                "fieldname": "entity_type",
                "fieldtype": "Data",
                "width": 120,
            },
        ]

    def get_columns(self):
        columns = super().get_columns()
        columns[1:1] = self.get_india_columns()
        return columns


execute = TaxWithholdingDetailsIndiaReport.execute
