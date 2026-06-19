// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["ISD Distribution Summary"] = {
    filters: [
        {
            fieldname: "show_distribution",
            label: __("Show Distribution"),
            fieldtype: "Check",
            default: 0,
            on_change: function () {
                // Check purchase invoices and go to distributed view -> auto filtering for checked purchase invoices
                const datatable = frappe.query_report.datatable;
                if (frappe.query_report.get_filter_value("show_distribution")) {
                    const checked = datatable ? datatable.rowmanager.getCheckedRows() : [];
                    const purchase_invoices = (checked || [])
                        .map((index) => frappe.query_report.data[index]?.purchase_invoice)
                        .filter(Boolean);

                    if (purchase_invoices.length) {
                        frappe.query_report.set_filter_value({ purchase_invoice: purchase_invoices });
                        datatable.rowmanager.checkAll(false);
                    }
                } else {
                    frappe.query_report.set_filter_value({ purchase_invoice: [] });
                    datatable?.rowmanager.checkAll(false);
                }
                frappe.query_report.refresh();
            },
        },
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            reqd: 1,
            default: frappe.defaults.get_user_default("Company"),
            on_change: function () {
                const company = frappe.query_report.get_filter_value("company");
                frappe.query_report.set_filter_value({ purchase_invoice: [] });
                frappe.call({
                    method: "india_compliance.gst_india.utils.isd.get_company_isd_gstin",
                    args: { company },
                    callback: function (r) {
                        frappe.query_report.set_filter_value({ company_gstin: r.message || "" });
                    },
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
        },
        {
            fieldname: "company_gstin",
            label: __("Company GSTIN"),
            fieldtype: "Autocomplete",
            depends_on: "eval:!doc.show_distribution",
            get_query() {
                const company = frappe.query_report.get_filter_value("company");
                return india_compliance.get_gstin_query(company);
            },
        },
        {
            fieldname: "purchase_invoice",
            label: __("Purchase Invoice"),
            fieldtype: "MultiSelectList",
            depends_on: "eval:doc.show_distribution",
            get_data: function (txt) {
                return frappe.db.get_link_options("Purchase Invoice", txt, {
                    company: frappe.query_report.get_filter_value("company"),
                    is_isd_applicable: 1,
                    docstatus: 1,
                });
            },
        },
        {
            fieldname: "pending_distribution",
            label: __("Pending Distribution"),
            fieldtype: "Check",
            default: 0,
            depends_on: "eval:!doc.show_distribution",
        },
    ],
    get_datatable_options(options) {
        return Object.assign(options, {
            checkboxColumn: true,
        });
    },
};
