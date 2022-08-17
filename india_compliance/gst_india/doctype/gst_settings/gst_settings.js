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
            return ic.get_gstin_query(row.company);
        });
    },
    onload: show_ic_api_promo,
    refresh(frm) {
        if (!frm.doc.__onload?.not_switched_to_simplified_tax) return;

        const message = __(`Are you sure you want to switch to simplified tax setup?
         This will remove all existing configurations for Tax Category. Read
         more about this in the <a href='#'>documentation</a>.`);

        frm.add_custom_button(__("Switch to simplified tax setup"), () => {
            frappe.confirm(message, () => {
                frappe.xcall(
                    "india_compliance.patches.post_install.remove_tax_category.switch_to_simplified_tax"
                );
            });
        });
    },
    attach_e_waybill_print(frm) {
        if (!frm.doc.attach_e_waybill_print || frm.doc.fetch_e_waybill_data) return;
        frm.set_value("fetch_e_waybill_data", 1);
    },
    auto_generate_e_invoice(frm) {
        if (!frm.doc.enable_e_invoice || !frm.doc.auto_generate_e_invoice) return;
        frm.set_value("auto_generate_e_waybill", 1);
    },
    enable_e_invoice(frm) {
        if (!frm.doc.enable_e_invoice || !frm.doc.auto_generate_e_invoice) return;
        frm.set_value("auto_generate_e_waybill", 1);
    },
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
