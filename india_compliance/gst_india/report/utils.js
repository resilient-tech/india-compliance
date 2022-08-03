function fetch_gstins(report) {
	const company = report.get_filter_value('company');
	const gstin_field = report.get_filter('company_gstin');

	if (!company) {
		gstin_field.df.options = [""];
		gstin_field.refresh();
        return;
	}

	frappe.call({
		method:'india_compliance.gst_india.utils.get_gstin_list',
		async: false,
		args: {
			party: company
		},
		callback(r) {
			r.message.unshift("");
			gstin_field.df.options = r.message;
			gstin_field.refresh();
		}
	});
}
