// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

const fy_bounds = india_compliance.get_indian_fiscal_year_bounds();

frappe.query_reports["MSME 43B(h) Disallowance"] = {
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
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            reqd: 1,
            default: fy_bounds.from_date,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            reqd: 1,
            default: fy_bounds.to_date,
        },
        {
            fieldname: "as_on_date",
            label: __("As On Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
        },
        {
            fieldname: "supplier",
            label: __("Supplier"),
            fieldtype: "Link",
            options: "Supplier",
        },
        {
            fieldname: "enterprise_type",
            label: __("Enterprise Type"),
            fieldtype: "Select",
            options: ["", "Micro", "Small"],
        },
    ],
};
