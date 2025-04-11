// Copyright (c) 2025, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["HSN-wise-summary of purchases"] = {
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
            fieldname: "gst_hsn_code",
            label: __("HSN/SAC"),
            fieldtype: "Link",
            options: "GST HSN Code",
            width: "80",
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
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            width: "80",
            default: india_compliance.last_month_start(),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            width: "80",
            default: india_compliance.last_month_end(),
            reqd: 1,
        },
    ],
    onload: report => {
        report.page.add_inner_button(__("Download JSON"), function () {
            var filters = report.get_values();

            frappe.call({
                method: "india_compliance.gst_india.report.hsn_wise_summary_of_purchases.hsn_wise_summary_of_purchases.get_json",
                args: {
                    data: report.data,
                    report_name: report.report_name,
                    filters: filters,
                },
                callback: function (r) {
                    if (r.message) {
                        const args = {
                            cmd: "india_compliance.gst_india.report.hsn_wise_summary_of_outward_supplies.hsn_wise_summary_of_outward_supplies.download_json_file",
                            data: r.message.data,
                            report_name: r.message.report_name,
                        };
                        open_url_post(frappe.request.url, args);
                    }
                },
            });
        });
    },
};
