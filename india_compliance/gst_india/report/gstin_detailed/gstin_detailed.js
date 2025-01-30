// Copyright (c) 2025, Resilient Tech and contributors
// For license information, please see license.txt


const COLUMNS = {
	2 : "status",
	3 : "registration_date",
	4 : "last_updated_on",
	5 : "cancelled_date",
	6 : "is_blocked",
}

frappe.query_reports["GSTIN Detailed"] = {
	filters: [
		{
			"fieldname": "status",
			"label": __("Status"),
			"fieldtype": "Select",
			"options": [
				"",
				"Active",
				"Cancelled",
				"Inactive",
				"Provisional",
				"Suspended",
			],
		},
		{
			"fieldname": "reference_party",
			"label": __("Reference Party"),
			"fieldtype": "Select",
			"options": [
				"",
				"Customer",
				"Supplier",
			],

		},

	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (data) {
			if (column.fieldname == "update_gstin_details_btn") {
				value = create_btn_with_gstin_attr(data.gstin);
			}
		}

		return default_formatter(value, row, column, data);
	},

	add_on_click_listner(gstin) {
		frappe.call({
			method: "india_compliance.gst_india.report.gstin_detailed.gstin_detailed.update_gstin_status",
			type: "GET",
			args: {
				gstin: gstin,
			},
			callback: function (r) {
				console.log(r);
				if (r.message) {
					let data = r.message;
					$(`[class="dt-cell__content dt-cell__content--col-1"][title='${gstin}']`)
						.each(function () {
							row = this.parentElement.attributes["data-row-index"].value;
							for (let col in COLUMNS) {
								update_value(row, col, COLUMNS[col])
							}
						})

				}
			}
		})
	},
};

function create_btn_with_gstin_attr(gstin) {
	const BUTTON_HTML = `<button data-fieldname="gstin_update_btn" class="btn btn-xs btn-primary center" data-gstin="${gstin}" onclick="frappe.query_reports['GSTIN Detailed'].add_on_click_listner('${gstin}')">Update</button>`;

	return BUTTON_HTML
}

function update_value(row, col, value) {
	let ele = $(`[class="dt-row dt-row-${row} vrow"] > [data-row-index="${row}"][data-col-index="${col}"] > div:first-child`);
	ele.attr("title", value)
	ele.text(value)
}
