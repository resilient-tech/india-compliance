frappe.ui.form.on("Subcontracting Order", {
    onload(frm) {
        frm.taxes_controller = new india_compliance.taxes_controller(frm);
    },

    taxes_and_charges(frm) {
        india_compliance.update_taxes(frm);
    },

    total_taxes(frm) {
        frm.taxes_controller.update_rounded_total(frm);
    },
});
