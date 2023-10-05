// Copyright (c) 2023, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["GST Advance Detail"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            reqd: 1,
            default: frappe.defaults.get_user_default("Company"),
            get_query: function () {
                return {
                    filters: {
                        country: "India",
                    },
                };
            },
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            depends_on: "eval:doc.show_for_period",
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.get_today(),
        },
        {
            fieldname: "customer",
            label: __("Customer"),
            fieldtype: "Link",
            options: "Customer",
        },
        {
            fieldname: "account",
            label: __("Account"),
            fieldtype: "Link",
            options: "Account",
            get_query: function () {
                var company = frappe.query_report.get_filter_value("company");
                return {
                    filters: {
                        company: company,
                        account_type: "Receivable",
                        is_group: 0,
                    },
                };
            },
        },
        {
            fieldname: "show_for_period",
            label: __("Show For Period"),
            fieldtype: "Check",
            default: 0,
        },
        {
            fieldname: "show_summary",
            label: __("Show Summary"),
            fieldtype: "Check",
            default: 0,
        }
    ],
};
