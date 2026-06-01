// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt
/* eslint-disable */
{% include "india_compliance/gst_india/report/utils.js" %}

const AMOUNT_FIELDS = [
    "taxable_value",
    "total_amount",
    "total_tax",
    "igst_amount",
    "cgst_amount",
    "sgst_amount",
    "cess_amount",
];

frappe.query_reports["GST Purchase Register"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            reqd: 1,
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
            fieldname: "filter_by",
            label: __("Filter By"),
            fieldtype: "Select",
            default: "ITC Claim Period",
            options: ["ITC Claim Period", "Posting Date"],
            reqd: 1,
        },
        {
            fieldtype: "Select",
            fieldname: "summary_by",
            label: __("Summary By"),
            options: "Overview\nSummary by Item\nSummary by Invoice",
            default: "Summary by Item",
        },
        {
            fieldtype: "Select",
            fieldname: "sub_section",
            label: __("Sub Section"),
            options: [
                { value: "4", label: __("Eligible ITC") },
                {
                    value: "5",
                    label: __("Values of exempt, nil rated and non-GST inward supplies"),
                },
            ],
            default: "4",
            reqd: 1,
        },
        {
            fieldtype: "MultiSelectList",
            fieldname: "invoice_sub_category",
            label: __("Invoice Sub Category"),
            depends_on: 'eval:doc.summary_by!=="Overview"',
            get_data: () => get_subcategory_options(),
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

function get_subcategory_options() {
    const sub_section = frappe.query_report.get_filter_value("sub_section");
    return get_inward_subcategory_options(sub_section);
}

function custom_report_column_total(...args) {
    const summary_by = frappe.query_report.get_filter_value("summary_by");
    if (summary_by === "Overview") return 0;

    const column_field = args[1].column.fieldname;
    if (!AMOUNT_FIELDS.includes(column_field)) return;

    const { data } = this.datamanager;
    return this.datamanager.getFilteredRowIndices().reduce((acc, index) => {
        const row = data[index];
        const value = row[column_field] || 0;
        if (row.invoice_category === "ITC Reversed") return acc - value;
        return acc + value;
    }, 0);
}
