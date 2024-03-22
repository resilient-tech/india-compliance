// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt
const invoice_type = {
    "B2B,SEZ,DE": ["", "4A", "4B", "6B", "6C"],
    "B2C (Large)": ["5"],
    "Exports": ["", "EXPWP", "EXPWOP"],
    "B2C (Others)": ["7"],
    "Nil Rated,Exempted,Non-GST": ["", "Nil-Rated", "Exempted", "Non-GST"],
    "Credit / Debit notes (Registered)": ["9B"],
    "Credit / Debit notes (Unregistered)": ["9B"],
}

let invoice_category=""
frappe.query_reports["GST Sales Register Beta"] = {
    "filters": [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            on_change: report => {
                report.set_filter_value({
                    company_gstin: "",
                });
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
            get_query: function () {
                const company = frappe.query_report.get_filter_value("company");
                return india_compliance.get_gstin_query(company);
            },
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            width: "80"
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today()
        },
        {
            fieldtype: "Select",
            fieldname: "summary_by",
            label: __("Summary By"),
            options: "Summary by HSN\nSummary by Item",
            default: "Summary by Item"
        },
        {
            fieldtype: "Autocomplete",
            fieldname: "invoice_category",
            label: __("Invoice Category"),
            options: "\nB2B,SEZ,DE\nB2C (Large)\nExports\nB2C (Others)\nNil Rated,Exempted,Non-GST\nCredit / Debit notes (Registered)\nCredit / Debit Notes (Unregistered)",
            on_change:(report)=>{
				report.set_filter_value('invoice_sub_category', "");

            }
        },
        {
            fieldtype: "Autocomplete",
            fieldname: "invoice_sub_category",
            label: __("Invoice Sub Category"),
            get_data:function(){
                const invoice_category=frappe.query_report.get_filter_value("invoice_category");
                return invoice_type[invoice_category];
            },

            // options:get_sub_category_options(frappe.query_report)

        }
    ]
};

function get_sub_category_options(report) {
    console.log(report)
    return invoice_type['B2B,SEZ,DE']
}