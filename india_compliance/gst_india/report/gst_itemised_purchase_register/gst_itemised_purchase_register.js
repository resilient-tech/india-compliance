// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt
/* eslint-disable */

{% include "erpnext/accounts/report/item_wise_purchase_register/item_wise_purchase_register.js" %}

frappe.query_reports["GST Itemised Purchase Register"] = frappe.query_reports["Item-wise Purchase Register"]
india_compliance.set_last_month_as_default_period(frappe.query_reports["GST Itemised Purchase Register"]);
