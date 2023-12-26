// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt
const TYPES_OF_BUSINESS = {
    B2B: __("B2B Invoices - 4A, 4B, 4C, 6B, 6C"),
    "B2C Large": __("B2C(Large) Invoices - 5A, 5B"),
    "B2C Small": __("B2C(Small) Invoices - 7"),
    "CDNR-REG": __("Credit/Debit Notes (Registered) - 9B"),
    "CDNR-UNREG": __("Credit/Debit Notes (Unregistered) - 9B"),
    EXPORT: __("Export Invoice - 6A"),
    Advances: __("Tax Liability (Advances Received) - 11A(1), 11A(2)"),
    Adjustment: __("Adjustment of Advances - 11B(1), 11B(2)"),
    "NIL Rated": __("NIL RATED/EXEMPTED Invoices"),
    "Document Issued Summary": __("Document Issued Summary"),
    HSN: __("HSN-wise-summary of outward supplies"),
};

const url = "india_compliance.gst_india.report.gstr_1.gstr_1";

frappe.query_reports["GSTR-1"] = {
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
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            reqd: 1,
            default: india_compliance.last_month_start(),
            width: "80",
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            reqd: 1,
            default: india_compliance.last_month_end(),
        },
        {
            fieldname: "type_of_business",
            label: __("Type of Business"),
            fieldtype: "Select",
            reqd: 1,
            options: Object.entries(TYPES_OF_BUSINESS).map(([value, label]) => ({
                value,
                label,
            })),
            default: "B2B",
            on_change: report => {
                report.page
                    .get_inner_group_button("Download as JSON")
                    .find(".dropdown-item")
                    .remove();
                report.page
                    .get_inner_group_button("Download as Excel")
                    .find(".dropdown-item")
                    .remove();
                create_download_buttons(report);
                report.refresh();
            },
        },
    ],
    onload: create_download_buttons,
};

function create_download_buttons(report) {
    report.page.add_inner_button(
        TYPES_OF_BUSINESS[report.get_values().type_of_business],
        () => download_current_report_json(report),
        __("Download as JSON")
    );

    report.page.add_inner_button(
        __("Full Report"),
        () => download_full_report_json(report),
        __("Download as JSON")
    );

    report.page.add_inner_button(
        TYPES_OF_BUSINESS[report.get_values().type_of_business],
        () => download_current_report_excel(report),
        __("Download as Excel")
    );

    report.page.add_inner_button(
        __("Full Report"),
        () => download_full_report_excel(report),
        __("Download as Excel")
    );
}

function download_current_report_json(report) {
    frappe.call({
        method: `${url}.get_gstr1_json`,
        args: {
            data: report.data,
            filters: report.get_values(),
        },
        callback: function (r) {
            if (r.message) {
                india_compliance.trigger_file_download(
                    JSON.stringify(r.message.data),
                    r.message.file_name
                );
            }
        },
    });
}

function download_full_report_json(report) {
    frappe.call({
        method: `${url}.get_gstr1_json`,
        args: {
            filters: report.get_values(),
        },
        callback: function (r) {
            if (r.message) {
                india_compliance.trigger_file_download(
                    JSON.stringify(r.message.data),
                    r.message.file_name
                );
            }
        },
    });
}

function download_current_report_excel(report) {
    open_url_post(`/api/method/${url}.get_gstr1_excel`, {
        data: JSON.stringify(report.data),
        filters: JSON.stringify(report.get_values()),
        columns: JSON.stringify(report.columns),
    });
}

function download_full_report_excel(report) {
    open_url_post(`/api/method/${url}.get_gstr1_excel`, {
        filters: JSON.stringify(report.get_values()),
    });
}
