const DOCTYPE = "Delivery Note";
setup_e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    onload(frm) {
        if (!is_e_waybill_applicable(frm)) return;
        show_sandbox_mode_indicator();
    },

    after_save(frm) {
        if (!is_e_waybill_generatable(frm)) return;

        frappe.show_alert(
            {
                message: __("Billing Address is required to create e-Waybill"),
                indicator: "yellow",
            },
            10
        );
    },
});
