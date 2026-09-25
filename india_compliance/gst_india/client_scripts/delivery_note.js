const DOCTYPE = "Delivery Note";
setup_e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    setup(frm) {
        frm.set_query("port_address", {
            filters: {
                country: "India",
            },
        });
    },
});
