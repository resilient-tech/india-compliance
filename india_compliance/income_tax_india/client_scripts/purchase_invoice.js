// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Purchase Invoice", {
    setup(frm) {
        frm.set_query("msme_registration", () => {
            return {
                query: "india_compliance.income_tax_india.overrides.purchase_invoice.get_valid_msme_registrations",
                filters: { posting_date: frm.doc.posting_date },
            };
        });
    },

    supplier(frm) {
        update_msme_details(frm);
    },
});

async function update_msme_details(frm) {
    if (frm.updating_party_details || frm.__updating_msme_details) return;

    // wait for ERPNext's own party fetch to land
    await frappe.after_ajax();

    frappe.call({
        method: "india_compliance.income_tax_india.overrides.purchase_invoice.get_msme_details",
        args: {
            party_details: JSON.stringify({ supplier: frm.doc.supplier }),
        },
        async callback(r) {
            if (!r.message) return;

            frm.__updating_msme_details = true;
            await frm.set_value(r.message);
            frm.__updating_msme_details = false;
        },
    });
}
