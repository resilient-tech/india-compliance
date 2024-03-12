// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["HSN-wise summary of inward supplies"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            width: "80",
            reqd : 1,
            default: india_compliance.last_month_start(),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            width: "80",
            reqd : 1,
            default: india_compliance.last_month_end(),
        },
        {
            fieldname: "company_address",
            label: __("Address"),
            fieldtype: "Link",
            options: "Address",
            get_query: function () {
                const company = frappe.query_report.get_filter_value("company");
                if (company) {
                    return {
                        query: "frappe.contacts.doctype.address.address.address_query",
                        filters: { link_doctype: "Company", link_name: company },
                    };
                }
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
    ],
};
