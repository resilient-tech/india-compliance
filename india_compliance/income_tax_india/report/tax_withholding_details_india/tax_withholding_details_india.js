// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

/* eslint-disable */
{% include "erpnext/accounts/report/tds_payable_monthly/tds_payable_monthly.js" %}

frappe.query_reports["Tax Withholding Details-India"] = frappe.query_reports["TDS Payable Monthly"];
