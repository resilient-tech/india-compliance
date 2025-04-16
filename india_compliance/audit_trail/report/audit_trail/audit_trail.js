// Copyright (c) 2023, Resilient Tech and contributors
// For license information, please see license.txt

const REPORT_TYPES = ["Detailed", "Summary by DocType", "Summary by User"];

const DATE_OPTIONS = [
    "Today",
    "Yesterday",
    "This Week",
    "This Month",
    "This Quarter",
    "This Year",
    "Last Week",
    "Last Month",
    "Last Quarter",
    "Last Year",
    "Custom",
];

frappe.query_reports["Audit Trail"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1,
        },
        {
            fieldname: "report",
            label: __("Report"),
            fieldtype: "Select",
            options: REPORT_TYPES,
            default: REPORT_TYPES[0],
            reqd: 1,
        },
        {
            label: __("Select Day"),
            fieldtype: "Select",
            fieldname: "date_option",
            options: DATE_OPTIONS,
            default: DATE_OPTIONS[0],
            reqd: 1,
            on_change: function (report) {
                let selected_value = report.get_filter_value("date_option");
                let date_range = report.get_filter("date_range");

                if (selected_value === "Custom") {
                    date_range.df.hidden = false;
                } else {
                    date_range.df.hidden = true;
                }
                date_range.refresh();
                report.refresh();
            },
        },
        {
            fieldname: "date_range",
            label: __("Select Dates"),
            fieldtype: "DateRange",
            hidden: true,
        },
        {
            fieldname: "user",
            label: __("User"),
            fieldtype: "Link",
            options: "User",
        },
        {
            fieldname: "doctype",
            label: __("DocType"),
            fieldtype: "Autocomplete",
            get_query: function () {
                return {
                    query: "india_compliance.audit_trail.report.audit_trail.audit_trail.get_relavant_doctypes",
                };
            },
        },
    ],
};
