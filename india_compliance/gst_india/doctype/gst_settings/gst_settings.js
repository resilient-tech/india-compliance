// Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt
const ALERT_HTML = `
    <div class="gst-account-changed-alert alert alert-primary fade show d-flex align-items-center justify-content-between border-0" role="alert">
        <div>
            Do you want to update Item GST Details based on GST Accounts
           <button id="run-patch-button" class="btn btn-primary btn-sm ml-2">
                Run patches
            </button>
        </div>
        <button type="button" class="close" data-dismiss="alert">
            <span aria-hidden="true">&times;</span>
        </button>
    </div>
`;

frappe.ui.form.on("GST Settings", {
    setup(frm) {
        [
            "cgst_account",
            "sgst_account",
            "igst_account",
            "cess_account",
            "cess_non_advol_account",
        ].forEach(field => filter_accounts(frm, field));

        const company_query = {
            filters: {
                country: "India",
            },
        };

        frm.set_query("company", "gst_accounts", company_query);
        frm.set_query("company", "credentials", company_query);
        frm.set_query("gstin", "credentials", (_, cdt, cdn) => {
            const row = frappe.get_doc(cdt, cdn);
            return india_compliance.get_gstin_query(row.company);
        });
    },
    onload: show_ic_api_promo,
    refresh: show_update_gst_category_button,
    attach_e_waybill_print(frm) {
        if (!frm.doc.attach_e_waybill_print || frm.doc.fetch_e_waybill_data) return;
        frm.set_value("fetch_e_waybill_data", 1);
    },
    enable_e_invoice: set_auto_generate_e_waybill,
    auto_generate_e_invoice: set_auto_generate_e_waybill,
    generate_e_waybill_with_e_invoice: set_auto_generate_e_waybill,
    before_save: async function (frm) {
        const { message } = await frm.call("check_gst_account_changes");
        frm.has_gst_account_changed = message
    },
    after_save(frm) {
        // sets latest values in frappe.boot for current user
        // other users will still need to refresh page
        Object.assign(gst_settings, frm.doc);
        show_gst_account_alert(frm);
    },
});

function show_gst_account_alert(frm) {
    if (!frm.has_gst_account_changed) return;
    //alert already exists
    if (frm.layout.wrapper.find(".gst-account-changed-alert").length !== 0) return;

    const alert_element = $(ALERT_HTML).prependTo(frm.layout.wrapper);

    alert_element
        .find("#run-patch-button")
        .on("click", () => open_patch_schedule_dialog(alert_element));
}

function open_patch_schedule_dialog(alert_element) {
    const dialog = new frappe.ui.Dialog({
        title: __("Schedule Patch Execution Time"),
        fields: [
            {
                label: "Execution Time",
                fieldname: "execution_time",
                fieldtype: "Datetime",
                default: `${frappe.datetime.add_days(
                    frappe.datetime.now_date(),
                    1
                )} 02:00:00`,
            },
        ],
        primary_action_label: __("Schedule"),
        primary_action(values) {
            if (values.execution_time < frappe.datetime.now_datetime()) {
                frappe.msgprint(__("Patch run time cannot be in the past"));
                return;
            }
            dialog.hide();
            frappe.call({
                method: "india_compliance.gst_india.doctype.gst_settings.gst_settings.schedule_gst_patches",
                args: { cron_time: values.execution_time },
            });
            alert_element.remove();
        },
    });
    dialog.show();
}

function filter_accounts(frm, account_field) {
    frm.set_query(account_field, "gst_accounts", (_, cdt, cdn) => {
        const row = frappe.get_doc(cdt, cdn);
        return {
            filters: {
                company: row.company,
                account_type: "Tax",
                is_group: 0,
            },
        };
    });
}

function show_ic_api_promo(frm) {
    if (!frm.doc.__onload?.can_show_promo) return;
    const alert_message = `
    Looking for API Features?
    <a href="/app/india-compliance-account" class="alert-link">
        Get started with the India Compliance API!
    </a>`;

    india_compliance.show_dismissable_alert(
        frm.layout.wrapper,
        alert_message,
        "primary",
        () => {
            frappe.xcall(
                "india_compliance.gst_india.doctype.gst_settings.gst_settings.disable_api_promo"
            );
        }
    );
}

function show_update_gst_category_button(frm) {
    if (
        !frappe.perm.has_perm(frm.doctype, 0, "write", frm.doc.name) ||
        !frm.doc.__onload?.has_missing_gst_category ||
        !india_compliance.is_api_enabled() ||
        !frm.doc.autofill_party_info
    )
        return;

    frm.add_custom_button(__("Update GST Category"), () => {
        frappe.msgprint({
            title: __("Update GST Category"),
            message: __(
                "Confirm to update GST Category for all Addresses where it is missing using API. It is missing for these <a><span class='custom-link' data-fieldtype='Link' data-doctype='Address'>Addresses</span><a>."
            ),
            primary_action: {
                label: __("Update"),
                server_action:
                    "india_compliance.gst_india.doctype.gst_settings.gst_settings.enqueue_update_gst_category",
                hide_on_success: true,
            },
        });

        $(document).on("click", ".custom-link", function () {
            const doctype = $(this).attr("data-doctype");

            frappe.route_options = {
                gst_category: ["is", "not set"],
            };

            frappe.set_route("List", doctype);
        });
    });
}

function set_auto_generate_e_waybill(frm) {
    if (!frm.doc.enable_e_invoice) return;

    frm.set_value(
        "auto_generate_e_waybill",
        frm.doc.auto_generate_e_invoice && frm.doc.generate_e_waybill_with_e_invoice
    );
}
