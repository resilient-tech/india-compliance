// Copyright (c) 2023, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("GSTIN", {
    refresh(frm) {
        frm.disable_form();

        frm.add_custom_button(__("Refresh Now"), () => {
            frm.call("update_gstin_status");
        });
    },
});
