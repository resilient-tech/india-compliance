// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt
/* eslint-disable */

{% include "erpnext/accounts/report/purchase_register/purchase_register.js" %}

frappe.query_reports["GST Purchase Register"] = frappe.query_reports["Purchase Register"]
india_compliance.set_last_month_as_default_period(frappe.query_reports["GST Purchase Register"]);