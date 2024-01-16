const DOCTYPE = "Sales Invoice";
setup_e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    setup(frm) {
        frm.set_query("transporter", {
            filters: {
                is_transporter: 1,
            },
        });

        frm.set_query("driver", doc => {
            return {
                filters: {
                    transporter: doc.transporter,
                },
            };
        });

        frm.set_query("port_address", {
            filters: {
                country: "India",
            },
        });
    },

    before_submit(frm) {
        frm.doc._submitted_from_ui = 1;
    },

    refresh(frm) {
        set_e_waybill_status_options(frm);

        if (!(gst_settings.enable_e_waybill || gst_settings.enable_e_invoice)) return;
        show_sandbox_mode_indicator();
    },

    after_save(frm) {
        if (
            frm.doc.customer_address ||
            frm.doc.is_return ||
            frm.doc.is_debit_note ||
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

function set_e_waybill_status_options(frm) {
    const options = ["Pending", "Not Applicable"];
    if (!options.includes(frm.doc.e_waybill_status)) {
        options.push(frm.doc.e_waybill_status);
    }
    set_field_options("e_waybill_status", options);
}
