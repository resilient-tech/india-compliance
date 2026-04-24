# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from erpnext.accounts.report.tds_computation_summary.tds_computation_summary import (
    execute as _execute,
)

from india_compliance.income_tax_india.report.tax_withholding_details_india.tax_withholding_details_india import (
    update_columns,
    update_data,
)


def execute(filters=None):
    _columns, _data = _execute(filters)
    data = update_data(_data)
    columns = update_columns(_columns)
    return columns, data
