// Copyright (c) 2025, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["Summary of ITC Availed"] = {
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
            columnTotal: function (...args) {
                const column_field = args[1].column.fieldname;
                if (column_field === "details") return "";

                const total = this.datamanager.data.reduce((acc, row) => {
                    if (row.indent === 0) {
                        acc += row[column_field] || 0;
                    }

                    return acc;
                }, 0);

                return total;
            },
        };

        return datatable_options;
    },
};
