// Copyright (c) 2023, Resilient Tech and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["GST Balance"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            on_change: report => {
                set_gstin_options(report);
                report.set_filter_value({
                    company_gstin: "",
                });
                add_custom_button_to_update_gstin(report);
            },
            reqd: 1,
        },
        {
            fieldname: "company_gstin",
            label: __("Company GSTIN"),
            fieldtype: "Autocomplete",
            get_data: () => set_gstin_options(frappe.query_report),
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.defaults.get_user_default("year_start_date"),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.defaults.get_user_default("year_end_date"),
        },
        {
            fieldname: "show_summary",
            label: __("Show Summary"),
            fieldtype: "Check",
            on_change: report => {
                toggle_filters(report);
                report.refresh();
            },
        },
    ],

    onload(report) {
        toggle_filters(report);
        set_gstin_options(report);
        add_custom_button_to_update_gstin(report);
    },
};

async function set_gstin_options(report) {
    const options = await india_compliance.get_gstin_options(
        report.get_filter_value("company")
    );
    const gstin_field = report.get_filter("company_gstin");
    gstin_field.set_data(options);

    if (options.length === 1) gstin_field.set_value(options[0]);
}

function toggle_filters(report) {
    const show_summary = report.get_filter_value("show_summary");
    report.get_filter("company_gstin").toggle(!show_summary);
    report.get_filter("from_date").toggle(!show_summary);
}

function add_custom_button_to_update_gstin(report) {
    frappe
        .call({
            method: "india_compliance.gst_india.report.gst_balance.gst_balance.get_pending_voucher_types",
            args: {
                company: report.get_filter_value("company"),
            },
        })
        .then(r => {
            if (!r.message) return;
            const [voucher_types, company_accounts] = r.message;
            if (!voucher_types.length) return;

            report._gst_accounts = company_accounts;
            report.page.add_inner_button(__("Update GSTIN"), () =>
                update_gstin_message(report, voucher_types)
            );
        });
}

async function update_gstin_message(report, voucher_types) {
    const message = get_update_gstin_message(report, voucher_types);
    frappe.msgprint({
        title: __("Update Company GSTIN"),
        message: message,
        primary_action: {
            label: __("Execute Patch"),
            server_action:
                "india_compliance.gst_india.report.gst_balance.gst_balance.update_company_gstin",
            hide_on_success: true,
        },
    });

    frappe.msg_dialog.custom_onhide = () => {
        report.refresh();
    };
}

function get_update_gstin_message(report, voucher_types) {
    // nosemgrep
    let message = __(
        `
        Company GSTIN is a mandatory field for all transactions.
        It could not be set automatically as you have Multi-GSTIN setup.
        Please update the GSTIN for the following transactions <strong>before</strong>
        executing the patch:<br>
        `
    );

    voucher_types.forEach(voucher_type => {
        let account_field = "account_head";
        if (voucher_type === "Journal Entry") account_field = "account";

        let element_text = `<br><a><span class="custom-link" data-fieldtype="Link" data-doctype="${voucher_type}" data-accountfield="${account_field}">${voucher_type}</span></a>`;
        message += element_text;
    });

    $(document).on("click", ".custom-link", function () {
        const doctype = $(this).data("doctype");
        const account_field = $(this).data("accountfield");

        frappe.set_route("List", doctype, {
            docstatus: 1,
            company_gstin: ["is", "not set"],
            [account_field]: ["in", report._gst_accounts],
        });
    });

    return message;
}
