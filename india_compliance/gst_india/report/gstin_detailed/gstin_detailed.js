// Copyright (c) 2025, Resilient Tech and contributors
// For license information, please see license.txt


const COLUMN_MAPPING = {
	2 : "status",
	3 : "registration_date",
	4 : "last_updated_on",
	5 : "cancelled_date",
	6 : "is_blocked",
}

frappe.query_reports["GSTIN Detailed"] = {

	html_enabled: true,

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
			"fieldname": "party_type",
			"label": __("Party Type"),
			"fieldtype": "Select",
			"options": [
				"",
				"Customer",
				"Supplier",
			],

		},

	],

	formatter: function (value, row, column, data, default_formatter) {
		if (data) {
			if(column.fieldname=="party_name"){
				column.options = data.party_type;
			}

			value = default_formatter(value, row, column, data);

			if(column.fieldtype === "Link"){
				return value;
			}

			if (column.fieldname == "update_gstin_details_btn") {
				value = create_btn_with_gstin_attr(data.gstin);
			}
			if(column.fieldtype === "Date"){
				return value;
			}
		}

		return value;
	},

	add_on_click_listner(gstin) {
		toggle_gstin_update_btn(gstin, disabled=true);
		const affectedElements = $(`[class="dt-cell__content dt-cell__content--col-1"][title='${gstin}']`);
		toggle_rows_opacity(affectedElements, opacity=0.5)

		frappe.call({
			method: "india_compliance.gst_india.report.gstin_detailed.gstin_detailed.update_gstin_status",
			args: {
				gstin: gstin,
			},
			callback: function (r) {
				if (r.message) {
					let data = r.message;
					affectedElements.each(function () {
						row = this.parentElement.attributes["data-row-index"].value;
						for (let col in COLUMN_MAPPING) {
							update_value(row, col, data[COLUMN_MAPPING[col]])
						}
					})
				}
				else{
					toggle_gstin_update_btn(gstin, disabled=false);
				}
				toggle_rows_opacity(affectedElements, opacity=1)
			}

		})
	},
};

function toggle_rows_opacity(elements, opacity=null){
	elements.each(function(){
		let row = this.parentElement.parentElement;
		if(opacity==null){
			opacity = row.style["opacity"];
			opacity = opacity===1?0.5:1;
		}
		row.style["opacity"] = opacity
	})
}

function toggle_gstin_update_btn(gstin, disabled=null){
	let btn = $(`button[data-gstin='${gstin}']`)
	if(disabled==null){
		disabled = btn.prop('disabled')
		disabled = !disabled
	}

	btn.prop("disabled", disabled)
}

function create_btn_with_gstin_attr(gstin) {
	const BUTTON_HTML = `<button data-fieldname="gstin_update_btn" class="btn btn-xs btn-primary center" data-gstin="${gstin}" onclick="frappe.query_reports['GSTIN Detailed'].add_on_click_listner('${gstin}')">Update</button>`;

	return BUTTON_HTML
}

function update_value(row, col, value) {
	let ele = $(`[class="dt-row dt-row-${row} vrow"] > [data-row-index="${row}"][data-col-index="${col}"] > div:first-child`);
	ele.attr("title", value)
	ele.text(value)
}
