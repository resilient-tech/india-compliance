// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Purchase Invoice", {
    onload: set_msme_registration_options,
    posting_date: set_msme_registration_options,
});

async function set_msme_registration_options(frm) {
    const field = frm.get_field("msme_registration");

    field.df.ignore_validation = true;

    const { message } = await frappe.call({
        method: "india_compliance.income_tax_india.utils.msme.get_msme_registration_options",
        args: { posting_date: frm.doc.posting_date },
    });

    field.set_data(message || []);
}
