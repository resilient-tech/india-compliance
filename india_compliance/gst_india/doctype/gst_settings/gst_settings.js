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
    attach_e_waybill_print(frm) {
        if (!frm.doc.attach_e_waybill_print || frm.doc.fetch_e_waybill_data) return;
        frm.set_value("fetch_e_waybill_data", 1);
    },
    enable_e_invoice: set_auto_generate_e_waybill,
    auto_generate_e_invoice: set_auto_generate_e_waybill,
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

    frm.set_value("auto_generate_e_waybill", frm.doc.auto_generate_e_invoice);
}
