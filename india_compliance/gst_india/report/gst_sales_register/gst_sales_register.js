// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

{% include "erpnext/accounts/report/sales_register/sales_register.js" %}

<<<<<<< HEAD
frappe.query_reports["GST Sales Register"] = frappe.query_reports["Sales Register"]
india_compliance.set_last_month_as_default_period(frappe.query_reports["GST Sales Register"]);
=======
frappe.query_reports["GST Sales Register"] = {
    onload: set_sub_category_options,

    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            on_change: (report) => {
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
            reqd: 1,
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
            fieldname: "date_range",
            label: __("Date Range"),
            fieldtype: "DateRange",
            default: [india_compliance.last_month_start(), india_compliance.last_month_end()],
            width: "80",
        },
        {
            fieldtype: "Select",
            fieldname: "summary_by",
            label: __("Summary By"),
            options: "Overview\nSummary by HSN\nSummary by Item",
            default: "Summary by Item",
        },
        {
            fieldtype: "Autocomplete",
            fieldname: "invoice_category",
            label: __("Invoice Category"),
            options: Object.keys(INVOICE_TYPE),
            on_change: (report) => {
                report.set_filter_value("invoice_sub_category", "");
                set_sub_category_options(report);
            },
            depends_on: 'eval:doc.summary_by=="Summary by HSN" || doc.summary_by=="Summary by Item"',
        },
        {
            fieldtype: "Autocomplete",
            fieldname: "invoice_sub_category",
            label: __("Invoice Sub Category"),
            depends_on: 'eval:doc.summary_by=="Summary by HSN" || doc.summary_by=="Summary by Item"',
        },
    ],

    formatter: (value, row, column, data, default_formatter) => {
        value = default_formatter(value, row, column, data);
        if (data && data.indent === 0) {
            let $value = $(`<span>${value}</span>`).css("font-weight", "bold");
            value = $value.wrap("<p></p>").parent().html();
        }

        return value;
    },

    // Override datatable hook for column total calculation
    get_datatable_options(datatable_options) {
        datatable_options.hooks = {
            columnTotal: custom_report_column_total,
        };

        return datatable_options;
    },
};

function set_sub_category_options(report) {
    const invoice_category = frappe.query_report.get_filter_value("invoice_category");
    report.get_filter("invoice_sub_category").set_data(INVOICE_TYPE[invoice_category] || []);

    if (invoice_category && INVOICE_TYPE[invoice_category].length === 1) {
        report.set_filter_value("invoice_sub_category", INVOICE_TYPE[invoice_category][0]);
    } else report.refresh();
}

function custom_report_column_total(...args) {
    const summary_by = frappe.query_report.get_filter_value("summary_by");
    if (summary_by !== "Overview") return frappe.utils.report_column_total.apply(this, args);

    const column_field = args[1].column.fieldname;
    if (column_field === "description") return;

    const { data } = this.datamanager;
    return this.datamanager.getFilteredRowIndices().reduce((acc, index) => {
        const row = data[index];
        if (row.indent === 1 || row.description === "Supplies made through E-commerce Operators") return acc;
        return acc + (row[column_field] || 0);
    }, 0);
}
>>>>>>> 2ebf8b3e (fix: optimize total calculation in custom report for filtered rows)
