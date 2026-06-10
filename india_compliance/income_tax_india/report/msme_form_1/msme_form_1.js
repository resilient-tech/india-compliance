// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["MSME Form-1"] = {
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
            fieldname: "period_fy",
            label: __("Financial Year"),
            fieldtype: "Autocomplete",
            options: india_compliance.get_indian_fiscal_year_options(),
            reqd: 1,
            default: india_compliance.get_indian_fiscal_year(),
        },
        {
            fieldname: "period",
            label: __("Period"),
            fieldtype: "Select",
            options: ["", "Apr-Sep", "Oct-Mar"],
            description: __("Leave blank for the full financial year"),
        },
        {
            fieldname: "group_by",
            label: __("Group By"),
            fieldtype: "Select",
            options: ["Invoice Wise", "Supplier Wise"],
            default: "Invoice Wise",
        },
    ],
};
