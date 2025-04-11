// Copyright (c) 2025, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["HSN-wise-summary of inward supplies"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            reqd: 1,
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
            fieldname: "gst_hsn_code",
            label: __("HSN/SAC"),
            fieldtype: "Link",
            options: "GST HSN Code",
            width: "80",
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
            width: "80",
            default: india_compliance.last_month_start(),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            width: "80",
            default: india_compliance.last_month_end(),
            reqd: 1,
        },
    ],
};
