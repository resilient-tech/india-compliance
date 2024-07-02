const FIELD_MAP = { tax_amount: "tax_amount" };

frappe.ui.form.on("Subcontracting Order", {
    setup(frm) {
        frm.set_query("taxes_and_charges", function () {
            return {
                filters: [
                    ["company", "=", frm.doc.company],
                    ["docstatus", "!=", 2],
                ],
            };
        });
    },
    onload(frm) {
        frm.taxes_controller = new india_compliance.taxes_controller(frm, FIELD_MAP);
    },

    taxes_and_charges(frm) {
        india_compliance.update_taxes(frm);
    },
});
