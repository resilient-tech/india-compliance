// Copyright (c) 2025, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["GSTIN Detailed"] = {
	filters: [
		{
			"fieldname": "status",
			"label": __("Status"),
			"fieldtype": "Select",
			"options": [
				"All",
				"Active",
				"Cancelled",
				"Inactive",
				"Provisional",
				"Suspended",
			],
			"default":"All",
		},
		{
			"fieldname": "reference_party",
			"label": __("Reference Party"),
			"fieldtype": "Select",
			"options": [
				"All",
				"Customer",
				"Supplier",
			],
			"default":"All",

		},

	],
};
