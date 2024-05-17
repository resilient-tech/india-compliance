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
    is_reverse_charge(frm) {
        if (frm.doc.ecommerce_gstin) {
            set_supply_liable_to(frm)
        }
    },
    ecommerce_gstin(frm) {
        if (!frm.doc.ecommerce_gstin) {
            frm.set_value("supply_liable_to", "")
            frm.set_df_property("supply_liable_to", "hidden", 1)

        }
        else {
            frm.set_df_property("supply_liable_to", "hidden", 0)
            set_supply_liable_to(frm)
        }

    }
});

function set_supply_liable_to(frm) {
    if (frm.doc.is_reverse_charge) {
        frm.set_value("supply_liable_to", "Reverse Charge u/s 9(5)")
    }
    else {
        frm.set_value("supply_liable_to", "Collect Tax u/s 52")
    }
}
