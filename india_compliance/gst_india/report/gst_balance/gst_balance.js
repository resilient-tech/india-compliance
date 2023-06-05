// Copyright (c) 2023, Resilient Tech and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["GST Balance"] = {
    filters: [
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
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.defaults.get_user_default("year_start_date"),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.defaults.get_user_default("year_end_date"),
        },
        {
            fieldname: "show_summary",
            label: __("Show Summary"),
            fieldtype: "Check",
            on_change: report => {
                toggle_filters(report);
                report.refresh();
            },
        },
    ],

    onload(report) {
        toggle_filters(report);
        set_gstin_options(report);
    },
};

async function set_gstin_options(report) {
    const options = await india_compliance.get_gstin_options(
        report.get_filter_value("company")
    );
    const gstin_field = report.get_filter("company_gstin");
    gstin_field.set_data(options);

    if (options.length == 1) gstin_field.set_value(options[0]);
}

function toggle_filters(report) {
    const show_summary = report.get_filter_value("show_summary");
    report.get_filter("company_gstin").toggle(!show_summary);
    report.get_filter("from_date").toggle(!show_summary);
}