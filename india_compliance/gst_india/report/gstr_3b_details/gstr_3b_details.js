// Copyright (c) 2023, Resilient Tech and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["GSTR-3B Details"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"reqd": 1,
			"default": frappe.defaults.get_user_default("Company")
		},
		{
			"fieldname": "company_gstin",
			"label": __("Company GSTIN"),
			"fieldtype": "Autocomplete",
			"reqd": 1,
			"get_query": function () {
				const company = frappe.query_report.get_filter_value('company');
				return india_compliance.get_gstin_query(company);
			}
		},
		{
			"fieldname": "year",
			"label": __("Year"),
			"fieldtype": "Select",
			"reqd": 1,
			"options": get_year_list(),
		},
		{
			"fieldname": "month_or_quarter",
			"label": __("Month or Quarter"),
			"fieldtype": "Select",
			"reqd": 1,
			"options": [
				"Apr - Jun",
				"Jul - Sep",
				"Oct - Dec",
				"Jan - Mar",
				"January",
				"February",
				"March",
				"April",
				"May",
				"June",
				"July",
				"August",
				"September",
				"October",
				"November",
				"December"
			  ],
		},
		{
			"fieldname": "section",
			"label": __("Section"),
			"fieldtype": "Select",
			"reqd": 1,
			"options": [
				{ "value": "4", "label": __("4. Eligible ITC") },
				{ "value": "5", "label": __("5. Values of exempt, nil rated and non-GST inward supplies") },
			],
		},

	],

}

function get_year_list() {
	const current_year = new Date().getFullYear();
	options = [current_year, current_year - 1, current_year - 2];
	return options;
}