// Copyright (c) 2025, Resilient Tech and contributors
// For license information, please see license.txt


const GSTIN_FIELDNAME_TO_FIELDTYPE_MAPPING = {
	"status": "Data",
	"registration_date": "Date",
	"last_updated_on": "Datetime",
	"cancelled_date": "Date",
	"is_blocked": "Data",
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
		console.log(row)
		console.log(column)
		console.log(data)
		if (data) {
			value = default_formatter(value, row, column, data);

			value = `<span fieldname="${column.fieldname}">${value}</span>`

			if (column.fieldname == "update_gstin_details_btn") {
				value = create_btn_with_gstin_attr(data.gstin);
			}
		}

		return value;
	},

	add_on_click_listner(gstin, default_formatter) {
		toggle_gstin_update_btn(gstin, disabled=true);
		const affectedElements = $(`div.dt-cell__content[title='${gstin}']`);
		toggle_rows_opacity(affectedElements, opacity=0.5)

		frappe.call({
			method: "india_compliance.gst_india.doctype.gstin.gstin.get_gstin_status",
			args: {
				gstin: gstin,
				force_update: true,
			},
			callback: function (r) {
				if (r.message) {
					let data = r.message;
					affectedElements.each(function () {
						row = this.parentElement.attributes["data-row-index"].value;
						for (let fieldname in GSTIN_FIELDNAME_TO_FIELDTYPE_MAPPING) {
							update_value(row, fieldname, GSTIN_FIELDNAME_TO_FIELDTYPE_MAPPING[fieldname], data[fieldname]);
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

function update_value(row, fieldname,fieldtype, value) {
	let ele = $(`.dt-row.dt-row-${row}.vrow > div > div > span[fieldname='${fieldname}']`);
	const formatter = frappe.form.get_formatter(fieldtype);
	value = formatter(value);
	if (fieldname == "is_blocked"){
		value = value==0?"No":"Yes";
	}
	ele.text(value);
	ele.parent().attr("title", value);
}
