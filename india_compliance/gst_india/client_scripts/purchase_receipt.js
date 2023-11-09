const DOCTYPE = "Purchase Receipt";
setup_e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    refresh(frm) {
        if (gst_settings.enable_e_waybill && gst_settings.enable_e_waybill_from_pr)
            show_sandbox_mode_indicator();
    },

    after_save(frm) {
        if (
            frm.doc.supplier_address ||
            !(frm.doc.gst_category == "Unregistered" || frm.doc.is_return) ||
            !is_e_waybill_applicable(frm) ||
            !has_e_waybill_threshold_met(frm)
        )
            return;

        frappe.show_alert(
            {
                message: __("Supplier Address is required to create e-Waybill"),
                indicator: "yellow",
            },
            10
        );
    },
});