const DOCTYPE = "Delivery Note";
setup_e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    onload(frm) {
        if (!gst_settings.enable_e_waybill) return;
        show_sandbox_mode_indicator();
    },

    after_save(frm) {
        if (
            frm.doc.customer_address ||
            !has_e_waybill_threshold_met(frm) ||
            !is_e_waybill_applicable(frm)
        )
            return;

        frappe.show_alert(
            {
                message: __("Billing Address is required to create e-Waybill"),
                indicator: "yellow",
            },
            10
        );
    },
});
