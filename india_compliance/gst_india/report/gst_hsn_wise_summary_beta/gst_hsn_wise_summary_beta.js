// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["GST HSN Wise Summary Beta"] = {
    filters: [
        {
            fieldname: "type_of_supplies",
            label: __("Type of Supplies"),
            fieldtype: "Select",
            options: ["Inward", "Outward"],
            reqd: 1,
        },
        {
            fieldtype: "Link",
            options: "Company",
            fieldname: "company",
            reqd: 1,
            label: __("Company"),
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
            get_query: function () {
                const company = frappe.query_report.get_filter_value("company");
                return india_compliance.get_gstin_query(company);
            },
        },
        {
            fieldname: "gst_hsn_code",
            label: __("HSN/SAC"),
            fieldtype: "Link",
            options: "GST HSN Code",
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            reqd: 1,
            default: india_compliance.last_month_start(),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            reqd: 1,
            default: india_compliance.last_month_end(),
        },
    ],
};
