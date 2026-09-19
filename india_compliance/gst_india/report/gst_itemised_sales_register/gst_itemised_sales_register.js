// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

{% include "erpnext/accounts/report/item_wise_sales_register/item_wise_sales_register.js" %}

let filters = frappe.query_reports["Item-wise Sales Register"]["filters"];

// Add GSTIN filter
filters = filters.concat({
    fieldname: "company_gstin",
    label: __("Company GSTIN"),
    fieldtype: "Autocomplete",
    width: "80",
    get_query() {
        const company = frappe.query_report.get_filter_value("company");
        return india_compliance.get_gstin_query(company);
    },
});

// Handle company on change
for (var i = 0; i < filters.length; ++i) {
    if (filters[i].fieldname === "company") {
        filters[i].on_change = (report) => india_compliance.set_gstin_filter_options(report);
    }
}

frappe.query_reports["GST Itemised Sales Register"] = {
    filters: filters,
    onload: (report) => india_compliance.set_gstin_filter_options(report),
};
india_compliance.set_last_month_as_default_period(frappe.query_reports["GST Itemised Sales Register"]);
