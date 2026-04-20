# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from erpnext.accounts.report.tds_computation_summary.tds_computation_summary import (
    _execute,
)

from india_compliance.income_tax_india.report.tax_withholding_details_india.tax_withholding_details_india import (
    get_additional_table_columns,
)


def execute(filters=None):
    return _execute(filters, additional_table_columns=get_additional_table_columns())
