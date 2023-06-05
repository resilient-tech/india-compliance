// Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("GST Settings", {
    setup(frm) {
        frm.get_field("credentials").grid.get_docfield("password").reqd = 1;

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
    refresh(frm) {
        if (frm.doc?.__onload?.voucher_types_for_gstin_update)
            show_update_gstin_button(frm);
    },
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

frappe.ui.form.on("GST Credential", {
    service(frm, cdt, cdn) {
        const doc = frappe.get_doc(cdt, cdn);
        const row = frm.get_field("credentials").grid.grid_rows_by_docname[doc.name];

        row.toggle_reqd("password", doc.service !== "Returns");
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

function set_auto_generate_e_waybill(frm) {
    if (!frm.doc.enable_e_invoice) return;

    frm.set_value(
        "auto_generate_e_waybill",
        frm.doc.auto_generate_e_invoice && frm.doc.generate_e_waybill_with_e_invoice
    );
}

// TEMPORARY CODE: trigger patch manually
function show_update_gstin_button(frm) {
    const voucher_types = frm.doc.__onload.voucher_types_for_gstin_update;

    frm.add_custom_button(__("Update Company GSTIN"), () => {
        const message = get_update_gstin_message(voucher_types);
        frappe.msgprint({
            title: __("Update Company GSTIN"),
            message: message,
            primary_action: {
                label: __("Execute Patch"),
                server_action:
                    "india_compliance.patches.post_install.update_company_gstin.execute",
                hide_on_success: true,
            },
        });

        frappe.msg_dialog.custom_onhide = () => {
            frm.reload_doc();
        };
    });
}

function get_update_gstin_message(voucher_types) {
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
            [account_field]: ["like", "%gst%"],
        });
    });

    return message;
}
