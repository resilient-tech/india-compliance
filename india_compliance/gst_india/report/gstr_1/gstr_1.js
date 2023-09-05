// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["GSTR-1"] = {
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
			"fieldname": "company_address",
			"label": __("Address"),
			"fieldtype": "Link",
			"options": "Address",
			"get_query": function () {
				const company = frappe.query_report.get_filter_value('company');
				if (company) {
					return {
						"query": 'frappe.contacts.doctype.address.address.address_query',
						"filters": { link_doctype: 'Company', link_name: company }
					};
				}
			}
		},
		{
			"fieldname": "company_gstin",
			"label": __("Company GSTIN"),
			"fieldtype": "Autocomplete",
			"get_query": function () {
				const company = frappe.query_report.get_filter_value('company');
				return india_compliance.get_gstin_query(company);
			}
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"reqd": 1,
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -3),
			"width": "80"
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"reqd": 1,
			"default": frappe.datetime.get_today()
		},
		{
			"fieldname": "type_of_business",
			"label": __("Type of Business"),
			"fieldtype": "Select",
			"reqd": 1,
			"options": [
				{ "value": "B2B", "label": __("B2B Invoices - 4A, 4B, 4C, 6B, 6C") },
				{ "value": "B2C Large", "label": __("B2C(Large) Invoices - 5A, 5B") },
				{ "value": "B2C Small", "label": __("B2C(Small) Invoices - 7") },
				{ "value": "CDNR-REG", "label": __("Credit/Debit Notes (Registered) - 9B") },
				{ "value": "CDNR-UNREG", "label": __("Credit/Debit Notes (Unregistered) - 9B") },
				{ "value": "EXPORT", "label": __("Export Invoice - 6A") },
				{ "value": "Advances", "label": __("Tax Liability (Advances Received) - 11A(1), 11A(2)") },
				{ "value": "NIL Rated", "label": __("NIL RATED/EXEMPTED Invoices") }
			],
			"default": "B2B",
			"on_change": (report) => {
				var $inner_group = report.page.get_inner_group_button("Download as JSON");
				var $drop_down_items = $inner_group.find(".dropdown-item");
				$drop_down_items.remove();
				create_download_buttons(report);
				report.refresh();
			},
		}
	],
	onload: (report) => {
		create_download_buttons(report);
	},
}

function create_download_buttons(report) {
	report.page.add_inner_button(
		__(`${report.get_values().type_of_business}`),
		() => download_current_report(report),
		`Download as JSON`
	);

	report.page.add_inner_button(
		__(`Complete Report`),
		() => download_complete_report(report),
		"Download as JSON"
	);
}


function download_current_report(report) {
	frappe.call({
		method: 'india_compliance.gst_india.report.gstr_1.gstr_1.get_json',
		args: {
			data: report.data,
			report_name: report.report_name,
			filters: report.get_values()
		},
		callback: function (r) {
			if (r.message) {
				const args = {
					cmd: 'india_compliance.gst_india.report.gstr_1.gstr_1.download_json_file',
					data: r.message.data,
					report_name: r.message.report_name,
					report_type: r.message.report_type
				};
				open_url_post(frappe.request.url, args);
			}
		}
	});
}

function download_complete_report(report) {
	frappe.call({
		method: 'india_compliance.gst_india.report.gstr_1.gstr_1.get_json_all_reports',
		args: {
			report_name: report.report_name,
			filters: report.get_values()
		},
		callback: function (r) {
			if (r.message) {
				const args = {
					cmd: 'india_compliance.gst_india.report.gstr_1.gstr_1.download_json_file',
					data: r.message.data,
					report_name: r.message.report_name,
					report_type: r.message.report_type
				};
				open_url_post(frappe.request.url, args);
			}
		}
	});
}
