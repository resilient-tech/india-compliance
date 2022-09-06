// Copyright (c) 2022, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["GST Balance"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            on_change: () => {
                set_gstin_options(frappe.query_report);
                set_account_options(frappe.query_report);
                frappe.query_report.set_filter_value({
                    company_gstin: "",
                    account: "",
                });
            },
            reqd: 1,
        },
        {
            fieldname: "company_gstin",
            label: __("Company GSTIN"),
            fieldtype: "Autocomplete",
            get_data: () => set_gstin_options(frappe.query_report),
        },
        {
            fieldname: "fiscal_year",
            label: __("Fiscal Year"),
            fieldtype: "Link",
            options: "Fiscal Year",
            default: frappe.defaults.get_user_default("fiscal_year"),
            reqd: 1,
            on_change: function (query_report) {
                var fiscal_year = query_report.get_values().fiscal_year;
                if (!fiscal_year) {
                    return;
                }
                frappe.model.with_doc("Fiscal Year", fiscal_year, function (r) {
                    var fy = frappe.model.get_doc("Fiscal Year", fiscal_year);
                    frappe.query_report.set_filter_value({
                        from_date: fy.year_start_date,
                        to_date: fy.year_end_date,
                    });
                });
            },
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.defaults.get_user_default("year_start_date"),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.defaults.get_user_default("year_end_date"),
        },
        {
            fieldname: "account",
            label: __("Account"),
            fieldtype: "Autocomplete",
            get_data: () => set_account_options(frappe.query_report),
        },
    ],
};

async function set_gstin_options(report) {
    const options = await ic.get_gstin_options(report.get_filter_value("company"));
    const gstin_field = report.get_filter("company_gstin");
    gstin_field.set_data(options);
}

async function set_account_options(report) {
    const options = await ic.get_account_options(report.get_filter_value("company"));
    const account_field = report.get_filter("account");
    account_field.set_data(options);
}
