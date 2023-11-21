// Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("GST Settings", {
    setup(frm) {
        ["cgst_account", "sgst_account", "igst_account", "cess_account"].forEach(
            field => filter_accounts(frm, field)
        );

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
    after_save(frm) {
        // sets latest values in frappe.boot for current user
        // other users will still need to refresh page
        Object.assign(gst_settings, frm.doc);
    },
});

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

    const alert = $(`
        <div
            class="alert alert-primary alert-dismissable fade show d-flex justify-content-between border-0"
            role="alert"
        >
            <div>
                Looking for API Features?
                <a href="/app/india-compliance-account" class="alert-link">
                    Get started with the India Compliance API!
                </a>
            </div>
            <button
                type="button"
                class="close"
                data-dismiss="alert"
                aria-label="Close"
                style="outline: 0px solid black !important"
            >
                <span aria-hidden="true">&times;</span>
            </button>
        </div>
    `).prependTo(frm.layout.wrapper);

    alert.on("closed.bs.alert", () => {
        frappe.xcall(
            "india_compliance.gst_india.doctype.gst_settings.gst_settings.disable_api_promo"
        );
    });
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
