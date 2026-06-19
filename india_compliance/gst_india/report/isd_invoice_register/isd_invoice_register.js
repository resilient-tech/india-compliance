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
                frappe.query_report.set_filter_value({
                    company_gstin: "",
                    distributor_gstin: "",
                    recipient_gstin: "",
                    purchase_invoice: "",
                });
            },
            get_query: function () {
                return { filters: { country: "India" } };
            },
        },
        {
            fieldname: "date_range",
            label: __("Date Range"),
            fieldtype: "DateRange",
            default: [india_compliance.last_month_start(), india_compliance.last_month_end()],
            reqd: 1,
            width: "80",
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
            fieldtype: "Autocomplete",
            depends_on: 'eval:doc.report_view === "ISD Invoice"',
            get_query() {
                const company = frappe.query_report.get_filter_value("company");
                return india_compliance.get_gstin_query(company);
            },
        },
        {
            fieldname: "recipient_gstin",
            label: __("Recipient GSTIN"),
            fieldtype: "Autocomplete",
            depends_on: 'eval:doc.report_view === "ISD Invoice"',
            get_query() {
                const company = frappe.query_report.get_filter_value("company");
                return india_compliance.get_gstin_query(company, "Company", true);
            },
        },
        {
            fieldname: "purchase_invoice",
            label: __("Purchase Invoice"),
            fieldtype: "Link",
            options: "Purchase Invoice",
            depends_on: 'eval:doc.report_view === "Purchase Invoice"',
            get_query() {
                const company = frappe.query_report.get_filter_value("company");
                return { filters: { company, is_isd_applicable: 1, docstatus: 1 } };
            },
        },
        {
            fieldname: "is_return",
            label: __("Is Return"),
            fieldtype: "Check",
            depends_on: 'eval:doc.report_view === "Purchase Invoice"',
        },
        {
            fieldname: "is_credit_note",
            label: __("Is Credit Note"),
            fieldtype: "Check",
            depends_on: 'eval:doc.report_view === "ISD Invoice"',
        },
        {
            fieldname: "recipient_state",
            label: __("Recipient State"),
            fieldtype: "Autocomplete",
            depends_on: 'eval:doc.report_view === "ISD Invoice"',
            options: frappe.boot.india_state_options,
        },
    ],
};
