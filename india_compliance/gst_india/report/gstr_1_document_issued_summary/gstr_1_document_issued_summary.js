// Copyright (c) 2022, Resilient Tech and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["GSTR-1 Document Issued Summary"] = {
	"filters": [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company")
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today()
		},
		{
			fieldname: "company_gstin",
			label: __("Company GSTIN"),
			fieldtype: "Data",
		},
		{
			fieldname: "company_address",
			label: __("Company Address"),
			fieldtype: "Link",
			options: "Address",
			get_query: function() {
				return {
					filters: {
						'is_your_company_address': 1
					}
				}
			}
		}
	]
};
