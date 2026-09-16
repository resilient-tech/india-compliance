// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Turnover Record", {
    onload(frm) {
        if (!frm.is_new()) return;

        const [, from_date, to_date] = erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true) || [];
        frm.set_value("from_date", from_date);
        frm.set_value("to_date", to_date);
    },
    refresh(frm) {
        set_gstin_options(frm);
        frm.get_field("gst_state").set_data(frappe.boot.india_state_options || []);
    },
    company(frm) {
        set_gstin_options(frm);
    },
    gstin(frm) {
        frm.set_value("gst_state", india_compliance.get_state_from_gstin(frm.doc.gstin));
    },
});

async function set_gstin_options(frm) {
    const company = frm.doc.company;
    const options = await india_compliance.get_gstin_options(company);
    frm.get_field("gstin").set_data(options || []);
}
