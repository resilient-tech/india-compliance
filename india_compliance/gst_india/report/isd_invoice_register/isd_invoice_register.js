// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["ISD Invoice Register"] = {
    filters: [
        {
            fieldname: "report_view",
            label: __("Report View"),
            fieldtype: "Select",
            options: "Purchase Invoice\nISD Invoice",
            default: "Purchase Invoice",
            reqd: 1,
            on_change: function () {
                frappe.query_report.refresh();
            },
        },
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            on_change: function () {
                frappe.query_report.set_filter_value("company_gstin", "");
            },
            get_query: function () {
                return { filters: { country: "India" } };
            },
        },
        {
            fieldname: "company_gstin",
            label: __("Company GSTIN"),
            fieldtype: "Autocomplete",
            depends_on: 'eval:doc.report_view === "Purchase Invoice"',
            get_query() {
                const company = frappe.query_report.get_filter_value("company");
                return india_compliance.get_gstin_query(company);
            },
        },
        {
            fieldname: "distributor_gstin",
            label: __("Distributor GSTIN"),
            fieldtype: "Data",
            depends_on: 'eval:doc.report_view === "ISD Invoice"',
        },
        {
            fieldname: "recipient_gstin",
            label: __("Recipient GSTIN"),
            fieldtype: "Data",
            depends_on: 'eval:doc.report_view === "ISD Invoice"',
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1,
        },
        {
            fieldname: "recipient_state",
            label: __("Recipient State"),
            fieldtype: "Autocomplete",
            depends_on: 'eval:doc.report_view === "ISD Invoice"',
            options: frappe.boot.india_state_options,
        },
        {
            fieldname: "is_return_only",
            label: __("Is Return Only"),
            fieldtype: "Check",
            depends_on: 'eval:doc.report_view === "Purchase Invoice"',
        },
        {
            fieldname: "is_credit_note_only",
            label: __("Is Credit Note Only"),
            fieldtype: "Check",
            depends_on: 'eval:doc.report_view === "ISD Invoice"',
        },
    ],
};
