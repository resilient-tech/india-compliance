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
            default: "Detailed",
            reqd: 1,
        },
        {
            label: __("Select Day"),
            fieldtype: "Select",
            fieldname: "date_option",
            options: DATE_OPTIONS,
            default: "This Week",
            reqd: 1,
            on_change: function (report) {
                if (report.get_filter_value("date_option") === "Custom") {
                    const date_range = report.get_filter("date_range");
                    date_range.df.reqd = 1;
                    date_range.set_required(1);
                }

                report.refresh();
            },
        },
        {
            fieldname: "date_range",
            label: __("Select Dates"),
            fieldtype: "DateRange",
            depends_on: "eval: doc.date_option === 'Custom'",
            default: [frappe.datetime.month_start(), frappe.datetime.now_date()],
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
                    query: "india_compliance.audit_trail.report.audit_trail.audit_trail.get_relevant_doctypes",
                };
            },
        },
    ],
};
