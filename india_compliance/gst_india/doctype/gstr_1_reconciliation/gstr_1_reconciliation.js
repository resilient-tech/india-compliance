// Copyright (c) 2025, Resilient Tech and contributors
// For license information, please see license.txt

const DOCTYPE = "GSTR-1 Reconciliation";

frappe.ui.form.on(DOCTYPE, {
    async setup(frm) {
        frappe.require("gstr1.bundle.js").then(() => {
            console.log("GSTR-1 Reconciliation Form Loaded");
        });
        set_default_company_gstin(frm);
    },

    refresh(frm) {
        frm.disable_save();
        frm.page.set_primary_action(__("Generate"), () => frm.trigger("generate"));
    },

    generate(frm) {
        console.log("Generating GSTR-1 Reconciliation");
        frm.taxpayer_api_call("get_gstr_1_reconciliation");
    },
});

async function set_default_company_gstin(frm) {
    frm.set_value("company_gstin", "");

    const company = frm.doc.company;
    if (!company) return;

    const { message: gstin_list } = await frappe.call(
        "india_compliance.gst_india.utils.get_gstin_list",
        { party: company }
    );

    if (gstin_list && gstin_list.length) {
        frm.set_value("company_gstin", gstin_list[0]);
    }
}
