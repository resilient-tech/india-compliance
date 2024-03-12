// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["GST Sales Register Beta"] = {
	"filters": [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			on_change: report => {
				set_gstin_options(report);
				report.set_filter_value({
					company_gstin: "",
				});

			},
			reqd: 1,
		},
		{
			fieldname: "company_gstin",
			label: __("Company GSTIN"),
			fieldtype: "Autocomplete",
			get_data: () => set_gstin_options(frappe.query_report),
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			"width": "80"
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today()
		},
		{
            fieldtype: "Select",
            fieldname: "summary_by",
            label: __("Summary By"),
            options: "Summary by HSN\nSummary by Item",
			default:"Summary by Item"
        },
		{
            fieldtype: "Select",
            fieldname: "invoice_type",
            label: __("Invoice Type"),
            options: "\nB2B\nB2C",
        }
	]
};

async function set_gstin_options(report) {
	const options = await india_compliance.get_gstin_options(
		report.get_filter_value("company")
	);
	const gstin_field = report.get_filter("company_gstin");
	gstin_field.set_data(options);

	// if (options.length === 1) gstin_field.set_value(options[0]);
}


