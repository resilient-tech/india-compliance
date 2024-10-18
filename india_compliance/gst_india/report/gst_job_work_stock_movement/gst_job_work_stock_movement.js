// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["GST Job Work Stock Movement"] = {
    filters: [
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
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: india_compliance.last_half_year("start"),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: india_compliance.last_half_year("end"),
            reqd: 1,
        },
        {
            fieldname: "category",
            label: __("Invoice Category"),
            fieldtype: "Select",
            options: [
                "Sent for Job Work (Table 4)",
                "Received back from Job Worker (Table 5A)",
            ],
            reqd: 1,
        },
    ],
    onload: function (query_report) {
        query_report.page.add_inner_button(__("Export JSON"), function () {
            this.dialog = new frappe.ui.Dialog({
                title: __("Export JSON"),
                fields: [
                    {
                        fieldname: "year",
                        label: __("Year"),
                        fieldtype: "Select",
                        options: get_options_for_year(),
                        onchange: () => {
                            if (this.dialog.get_value("year") === "2017") {
                                this.dialog.fields_dict.period.df.options = [
                                    "Jul - Sep",
                                    "Oct - Dec",
                                    "Jan - Mar",
                                ];
                                this.dialog.refresh();
                            }
                        },
                    },
                    {
                        fieldname: "period",
                        label: __("Return Filing Period"),
                        fieldtype: "Select",
                        options: ["Apr - Jun", "Jul - Sep", "Oct - Dec", "Jan - Mar"],
                    },
                ],
                primary_action_label: "Export JSON",
                primary_action: () => {
                    frappe.call({
                        method: "india_compliance.gst_india.utils.itc_04.itc_04_export.download_itc_04_json",
                        args: {
                            company: frappe.query_report.get_filter_value("company"),
                            company_gstin:
                                frappe.query_report.get_filter_value("company_gstin"),
                            period: this.dialog.get_value("period"),
                            year: this.dialog.get_value("year"),
                        },
                        callback: r => {
                            this.dialog.hide();
                            india_compliance.trigger_file_download(
                                JSON.stringify(r.message.data),
                                r.message.filename
                            );
                        },
                    });
                },
            });

            dialog.show();
        });
        query_report.refresh();
    },
};

function get_options_for_year() {
    const today = new Date();
    const current_year = today.getFullYear();
    const start_year = 2017;
    const year_range = current_year - start_year + 1;
    let options = Array.from({ length: year_range }, (_, index) => start_year + index);
    return options.reverse().map(year => year.toString());
}
