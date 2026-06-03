// Copyright (c) 2023, Resilient Tech and contributors
// For license information, please see license.txt
/* eslint-disable */

const AMOUNT_FIELDS = ["igst_amount", "cgst_amount", "sgst_amount", "cess_amount", "intra", "inter"];

frappe.query_reports["GSTR-3B Details"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            reqd: 1,
            default: frappe.defaults.get_user_default("Company"),
        },
        {
            fieldname: "company_gstin",
            label: __("Company GSTIN"),
            fieldtype: "Autocomplete",
            reqd: 1,
            get_query: function () {
                const company = frappe.query_report.get_filter_value("company");
                return india_compliance.get_gstin_query(company);
            },
        },
        {
            fieldname: "year",
            label: __("Year"),
            fieldtype: "Select",
            reqd: 1,
            default: get_default_option(),
            options: get_options(),
        },
        {
            fieldname: "month_or_quarter",
            label: __("Month or Quarter"),
            fieldtype: "Select",
            reqd: 1,
            default: india_compliance.last_month_name(),
            options: [
                "Apr - Jun",
                "Jul - Sep",
                "Oct - Dec",
                "Jan - Mar",
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ],
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
            fieldname: "sub_section",
            label: __("Sub Section"),
            fieldtype: "Select",
            reqd: 1,
            default: "4",
            options: [
                { value: "4", label: __("4. Eligible ITC") },
                {
                    value: "5",
                    label: __("5. Values of exempt, nil rated and non-GST inward supplies"),
                },
            ],
        },
        {
            fieldtype: "MultiSelectList",
            fieldname: "invoice_sub_category",
            label: __("Invoice Sub Category"),
            get_data: () => get_subcategory_options(),
        },
    ],

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
    return india_compliance.get_inward_subcategory_options(sub_section);
}

function custom_report_column_total(...args) {
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

function get_default_option() {
    return india_compliance.get_options_for_year("Monthly").current_year;
}

function get_options() {
    return india_compliance.get_options_for_year("Monthly").options.slice(0, 3);
}
