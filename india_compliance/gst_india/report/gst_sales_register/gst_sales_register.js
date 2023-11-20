// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt
/* eslint-disable */

{% include "erpnext/accounts/report/sales_register/sales_register.js" %}

frappe.query_reports["GST Sales Register"] = frappe.query_reports["Sales Register"]
india_compliance.set_last_month_as_default_period(frappe.query_reports["GST Sales Register"]);