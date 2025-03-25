// Copyright (c) 2023, Resilient Tech and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["GSTR-3B Details"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            reqd: 1,
            default: frappe.defaults.get_user_default("Company"),
        },
        {
            fieldname: "company_gstin",
            label: __("Company GSTIN"),
            fieldtype: "Autocomplete",
            reqd: 1,
            get_query: function () {
                const company = frappe.query_report.get_filter_value("company");
                return india_compliance.get_gstin_query(company);
            },
        },
        {
            fieldname: "year",
            label: __("Year"),
            fieldtype: "Select",
            reqd: 1,
            default: get_default_option(),
            options: get_options(),
        },
        {
            fieldname: "month_or_quarter",
            label: __("Month or Quarter"),
            fieldtype: "Select",
            reqd: 1,
            default: india_compliance.last_month_name(),
            options: [
                "Apr - Jun",
                "Jul - Sep",
                "Oct - Dec",
                "Jan - Mar",
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ],
        },
        {
            fieldname: "section",
            label: __("Section"),
            fieldtype: "Select",
            reqd: 1,
            default: "4",
            options: [
                { value: "4", label: __("4. Eligible ITC") },
                {
                    value: "5",
                    label: __(
                        "5. Values of exempt, nil rated and non-GST inward supplies"
                    ),
                },
            ],
        },
    ],
};

function get_default_option() {
    return india_compliance.get_options_for_year("Monthly").current_year;
}

function get_options() {
    return india_compliance.get_options_for_year("Monthly").options.slice(0, 3);
}
