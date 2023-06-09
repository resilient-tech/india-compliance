const DOCTYPE = "Delivery Note";
setup_e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    after_save(frm) {
        if (
            frm.doc.docstatus ||
            frm.doc.customer_address ||
            !(gst_settings.enable_e_waybill && gst_settings.enable_e_waybill_from_dn)
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

    refresh(frm) {
        frm.set_df_property("port_code", "ignore_validation", 1);
        india_compliance.set_port_code_options(frm);
    },
});
