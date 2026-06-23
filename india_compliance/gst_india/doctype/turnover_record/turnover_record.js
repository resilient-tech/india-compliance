// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Turnover Record", {
    async onload(frm) {
        // TODO: ux update (isd phase 2)
        if (frm.is_new()) {
            await _set_default_fiscal_year_dates(frm);
        }
        frm.get_field("gst_state").set_data(frappe.boot.india_state_options || []);
    },

    gstin(frm) {
        if (!frm.doc.gstin) return;
        india_compliance.validate_gstin(frm.doc.gstin);
        frm.doc.gst_category = india_compliance.guess_gst_category(frm.doc.gstin, "India");
    },

    from_date(frm) {
        if (!frm.doc.from_date) return;
        const from_year = parseInt(frm.doc.from_date.split("-")[0]);
        frm.set_value("to_date", `${from_year + 1}-03-31`);
    },

    to_date(frm) {
        if (!frm.doc.to_date) return;
        const to_year = parseInt(frm.doc.to_date.split("-")[0]);
        frm.set_value("from_date", `${to_year - 1}-04-01`);
    },
});

async function _set_default_fiscal_year_dates(frm) {
    const fy = await erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true);
    if (!fy) return;
    frm.set_value("from_date", fy[1]);
}
