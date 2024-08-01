// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Pan", {
    refresh(frm) {
        frm.add_custom_button(__("Refresh PAN Status"), () => {
            frm.call("update_pan_status");
        });
    },
    pan(frm) {
        frm.doc.pan = frm.doc.pan.toUpperCase();
    },
});
