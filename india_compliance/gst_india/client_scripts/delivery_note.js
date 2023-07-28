const DOCTYPE = "Delivery Note";
setup_e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    refresh (frm) {
        show_sandbox_mode_indicator();
    },

    after_save(frm) {
        if (
            frm.doc.docstatus ||
            frm.doc.customer_address ||
            !(gst_settings.enable_e_waybill && gst_settings.enable_e_waybill_from_dn)
        )
            return;

        frappe.show_alert({
            message: __("Billing Address is required to create e-Waybill"),
            indicator: "yellow",
        }, 10);
    },
});
