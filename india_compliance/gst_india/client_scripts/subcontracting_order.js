frappe.ui.form.on("Subcontracting Order", {
    onload(frm) {
        frm.taxes_controller = new india_compliance.taxes_controller(frm);
    },

    taxes_and_charges(frm) {
        india_compliance.update_taxes(frm);
    },
});
