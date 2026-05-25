// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Turnover Record", {
    gstin(frm) {
        if (!frm.doc.gstin) return;
        india_compliance.validate_gstin(frm.doc.gstin);
        frm.doc.gst_category = india_compliance.guess_gst_category(frm.doc.gstin, "India");
    },
});
