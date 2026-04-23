# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from erpnext.accounts.report.tds_computation_summary.tds_computation_summary import (
    TDSComputationSummaryReport,
)

from india_compliance.income_tax_india.report.tax_withholding_details_india.tax_withholding_details_india import (
    TWC_INDIA_FIELDS,
    TaxWithholdingDetailsIndiaReport,
)


class TDSComputationSummaryIndiaReport(TaxWithholdingDetailsIndiaReport, TDSComputationSummaryReport):
    CARRY_OVER_FIELDS = TDSComputationSummaryReport.CARRY_OVER_FIELDS + TWC_INDIA_FIELDS


execute = TDSComputationSummaryIndiaReport.execute
