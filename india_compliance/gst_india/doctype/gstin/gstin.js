// Copyright (c) 2023, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("GSTIN", {
    refresh(frm) {
        frm.disable_form();

        frm.add_custom_button(__("Refresh GSTIN Status"), () => {
            frm.call("update_gstin_status");
        });

        frm.add_custom_button(__("Refresh Transporter ID Status"), () => {
            frm.call("update_transporter_id_status");
        });
    },
});
