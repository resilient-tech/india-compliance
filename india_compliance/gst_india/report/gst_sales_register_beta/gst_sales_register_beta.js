// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt
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
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            "width": "80"
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today()
        },
        {
            fieldtype: "Select",
            fieldname: "summary_by",
            label: __("Summary By"),
            options: "Summary by HSN\nSummary by Item",
            default: "Summary by Item"
        },
        {
            fieldtype: "Select",
            fieldname: "invoice_category",
            label: __("Invoice Category"),
            options: "\nNil-Rated\nExempted\nNon-GST\nCredit/Debit Notes Registered (CDNR)\nCredit/Debit Notes Unregistered (CDNUR)\nB2B\nB2C(Large)\nB2C(Small)\nExport Invoice",
        }
    ]
};



