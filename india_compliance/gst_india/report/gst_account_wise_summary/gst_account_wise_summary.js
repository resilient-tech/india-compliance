// Copyright (c) 2025, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["GST Account-wise Summary"] = {
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
                        is_group: 0,
                    },
                };
            },
        },
        {
            fieldname: "company_gstin",
            label: __("Company GSTIN"),
            fieldtype: "Autocomplete",
            get_query: function () {
                const company = frappe.query_report.get_filter_value("company");
                return india_compliance.get_gstin_query(company);
            },
        },
        {
            fieldname: "date_range",
            label: __("Date Range"),
            fieldtype: "DateRange",
            default: [
                india_compliance.last_month_start(),
                india_compliance.last_month_end(),
            ],
            reqd: 1,
            width: "80",
        },
        {
            fieldname: "voucher_type",
            label: __("Voucher Type"),
            fieldtype: "Select",
            reqd: 1,
            default: "Sales",
            options: ["Purchase", "Sales"],
        },
    ],
};
