// Copyright (c) 2023, Resilient Tech and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Audit Trail"] = {
    filters: [
        {
            fieldname: "report",
            label: __("Report"),
            fieldtype: "Select",
            options: "Detailed\nSummary by Doctype\nSummary by User",
            default: "Detailed",
            reqd: 1,
        },
        {
            label: __("Select Day"),
            fieldtype: "Select",
            fieldname: "date_option",
            default: "Today",
            options:
                "Today\nYesterday\nThis Week\nThis Month\nThis Quarter\nThis Year\nLast Week\nLast Month\nLast Quarter\nLast Year\nCustom",
            reqd: 1,
            on_change: function (report) {
                var selected_value = report.get_filter_value("date");
                var date_range = report.get_filter("date_range");

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
            label: __("Select Date"),
            fieldtype: "DateRange",
            hidden: true,
        },
        {
            fieldname: "user",
            label: __("User"),
            fieldtype: "Link",
            default: "",
            options: "User",
            //reqd: 1
        },
        {
            fieldname: "doctype",
            label: __("Based On"),
            fieldtype: "Autocomplete",
            default: "",
            get_query: function () {
                return {
                    query: "india_compliance.audit_trail.utils.get_audit_trail_doctypes",
                    filters: {},
                };
            },
        },
    ],
};
