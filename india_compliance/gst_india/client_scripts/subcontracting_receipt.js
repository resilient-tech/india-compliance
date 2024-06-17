setup_e_waybill_actions("Subcontracting Receipt");

frappe.ui.form.on("Subcontracting Receipt", {
    onload(frm) {
        frm.taxes_controller = new india_compliance.taxes_controller(frm);
    },

    refresh(frm) {
        if (!gst_settings.enable_e_waybill || !gst_settings.enable_e_waybill_for_sc)
            return;
        show_sandbox_mode_indicator();
    },

    after_save(frm) {
        if (is_e_waybill_applicable(frm) && !is_e_waybill_generatable(frm))
            frappe.show_alert(
                {
                    message: __("E-Way Bill is not generatable for this transaction"),
                    indicator: "yellow",
                },
                10
            );
    },

    taxes_and_charges(frm) {
        india_compliance.update_taxes(frm);
    },

    total_taxes(frm) {
        frm.taxes_controller.update_rounded_total(frm);
    },
});
