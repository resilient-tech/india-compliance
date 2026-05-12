// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["ISD Distribution Summary"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "company_gstin",
			label: __("Company GSTIN"),
			fieldtype: "Data",
			depends_on: "company",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "pending_distribution",
			label: __("Pending Distribution"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
