// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["GST Job Work Stock Movement"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            on_change: report => {
                report.set_filter_value({
                    company_gstin: "",
                });
                report.refresh();
            },
            get_query: function () {
                return {
                    filters: {
                        country: "India",
                    },
                };
            },
        },
        {
            fieldname: "company_gstin",
            label: __("Company GSTIN"),
            fieldtype: "Autocomplete",
            get_query() {
                const company = frappe.query_report.get_filter_value("company");
                return india_compliance.get_gstin_query(company);
            },
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: india_compliance.last_half_year("start"),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: india_compliance.last_half_year("end"),
            reqd: 1,
        },
        {
            fieldname: "category",
            label: __("Invoice Category"),
            fieldtype: "Select",
            options: [
                "Sent for Job Work (Table 4)",
                "Received back from Job Worker (Table 5A)",
            ],
            reqd: 1,
        },
    ],
};
