const DOCTYPE = "Delivery Note";
setup_e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    refresh(frm) {
        if (!gst_settings.enable_e_waybill || !gst_settings.enable_e_waybill_from_dn)
            return;
        show_sandbox_mode_indicator();
    },

    after_save(frm) {
        if (is_e_waybill_applicable(frm) && !is_e_waybill_generatable(frm))
            frappe.show_alert(
                {
                    message: __("Billing Address is required to create e-Waybill"),
                    indicator: "yellow",
                },
                10
            );
    },
});
