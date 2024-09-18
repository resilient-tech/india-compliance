// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt
const SUB_SECTION_MAPPING = {
    4: {
        "ITC Available": [
            "Import Of Goods",
            "Import Of Service",
            "ITC on Reverse Charge",
            "Input Service Distributor",
            "All Other ITC",
        ],
        "ITC Reversed": ["As per rules 42 & 43 of CGST Rules", "Others"],
        "Ineligible ITC": ["Ineligible As Per Section 17(5)", "Others"],
    },
    5: {
        "Composition Scheme, Exempted, Nil Rated": [
            "Composition Scheme, Exempted, Nil Rated",
        ],
        "Non-GST": ["Non-GST"],
    },
};

frappe.query_reports["GST Purchase Register Beta"] = {
    onload: set_category_options,

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
            reqd: 1,
            get_query() {
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
            width: "80",
        },
        {
            fieldtype: "Select",
            fieldname: "summary_by",
            label: __("Summary By"),
            options: "Overview\nSummary by Item\nSummary by Invoice",
            default: "Overview",
        },
        {
            fieldtype: "Select",
            fieldname: "sub_section",
            label: __("Sub Section"),
            options: [
                { value: "4", label: __("Eligible ITC") },
                {
                    value: "5",
                    label: __(
                        "Values of exempt, nil rated and non-GST inward supplies"
                    ),
                },
            ],
            default: "4",
            reqd: 1,
            on_change: report => {
                report.set_filter_value("invoice_category", "");
                set_category_options(report);
                report.refresh();
            },
        },
        {
            fieldtype: "Autocomplete",
            fieldname: "invoice_category",
            label: __("Invoice Category"),
            on_change: report => {
                report.set_filter_value("invoice_sub_category", "");
                set_sub_category_options(report);
                report.refresh();
            },
            depends_on: 'eval:doc.summary_by!=="Overview"',
        },
        {
            fieldtype: "Autocomplete",
            fieldname: "invoice_sub_category",
            label: __("Invoice Sub Category"),
            depends_on: 'eval:doc.summary_by!=="Overview"',
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
    const invoice_category = report.get_filter_value("invoice_category");
    const sub_section = report.get_filter_value("sub_section");
    const sub_category = SUB_SECTION_MAPPING[sub_section][invoice_category];
    report.get_filter("invoice_sub_category").set_data(sub_category || []);

    if (invoice_category && sub_category.length === 1) {
        report.set_filter_value("invoice_sub_category", sub_category[0]);
    }
}

function set_category_options(report) {
    const sub_section = report.get_filter_value("sub_section");
    report
        .get_filter("invoice_category")
        .set_data(Object.keys(SUB_SECTION_MAPPING[sub_section]));
}

custom_report_column_total = function (...args) {
    const summary_by = frappe.query_report.get_filter_value("summary_by");
    if (summary_by !== "Overview")
        return frappe.utils.report_column_total.apply(this, args);

    const column_field = args[1].column.fieldname;
    if (column_field === "description") return;

    const total = this.datamanager.data.reduce((acc, row) => {
        if (row.indent !== 1) acc += row[column_field] || 0;
        return acc;
    }, 0);

    return total;
};
