// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Turnover Record", {
    refresh(frm) {
        set_gstin_options(frm);
    },
});

async function set_gstin_options(frm) {
    const company = frappe.defaults.get_user_default("Company");
    if (!company) return;

    const options = await india_compliance.get_gstin_options(company);
    frm.get_field("gstin").set_data(options || []);
}
