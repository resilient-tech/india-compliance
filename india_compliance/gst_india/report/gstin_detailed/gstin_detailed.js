// Copyright (c) 2025, Resilient Tech and contributors
// For license information, please see license.txt

BUTTON_HTML = `
<button data-fieldname="gstin_update_btn" class="btn btn-xs btn-primary center">
	Update
</button>`;

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

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (data) {
			if (column.fieldname === "update_gstin_details_btn") {
				value = BUTTON_HTML;
			}
		}

		return value;
	},
};
