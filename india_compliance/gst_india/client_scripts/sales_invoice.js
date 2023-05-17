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
    }
});
