setup_e_waybill_actions("Subcontracting Receipt");

frappe.ui.form.on("Subcontracting Receipt", {
    setup(frm) {
        frm.set_query("taxes_and_charges", function () {
            return {
                filters: [
                    ["disabled", "=", 0],
                    ["company", "=", frm.doc.company],
                ],
            };
        });

        frm.set_query("transporter", function () {
            return {
                filters: [
                    ["disabled", "=", 0],
                    ["is_transporter", "=", 1],
                ],
            };
        });

        ["supplier_address", "shipping_address"].forEach(field => {
            frm.set_query(field, function () {
                return { filters: { country: "India", disabled: 0 } };
            });
        });
    },
    onload(frm) {
        frm.taxes_controller = new india_compliance.taxes_controller(frm, {
            total_taxable_value: "total",
        });
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
                    message: __("Supplier Address is required to create e-Waybill"),
                    indicator: "yellow",
                },
                10
            );
    },

    taxes_and_charges(frm) {
        frm.taxes_controller.update_taxes(frm);
    },
});

frappe.ui.form.on(
    "Subcontracting Receipt Item",
    india_compliance.taxes_controller_events
);
