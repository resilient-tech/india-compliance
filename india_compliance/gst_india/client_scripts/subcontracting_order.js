frappe.ui.form.on("Subcontracting Order", {
    setup(frm) {
        frm.set_query("taxes_and_charges", function () {
            return {
                filters: [
                    ["disabled", "=", 0],
                    ["company", "=", frm.doc.company],
                ],
            };
        });
    },
    onload(frm) {
        frm.taxes_controller = new india_compliance.taxes_controller(frm, {
            total_taxable_value: "total",
        });

        frm.get_docfield("taxes", "charge_type").options = [
            "On Net Total",
            "On Item Quantity",
        ];
    },

    taxes_and_charges(frm) {
        frm.taxes_controller.update_taxes(frm);
    },
});

frappe.ui.form.on(
    "Subcontracting Order Item",
    india_compliance.taxes_controller_events
);
